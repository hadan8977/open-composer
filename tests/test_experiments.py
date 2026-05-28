from __future__ import annotations

from pathlib import Path

from open_composer.experiments import (
    append_experiment_run,
    artifact_ref,
    compare_experiment_runs,
    experiment_artifacts,
    read_experiment_runs,
    trace_experiment_runs,
)
from open_composer.models.experiment import ExperimentRun
from open_composer.storage import write_json


def test_experiment_index_records_and_compares_runs(sample_workspace: Path) -> None:
    append_experiment_run(
        ExperimentRun(
            run_id="run-a",
            name="A",
            kind="unit",
            strategy_name="fixture",
            status="ok",
            gate_status="ok",
            metrics={"return_pct": 1.0},
        ),
        sample_workspace,
    )
    append_experiment_run(
        ExperimentRun(
            run_id="run-b",
            name="B",
            kind="unit",
            strategy_name="fixture",
            status="warning",
            gate_status="warning",
            metrics={"return_pct": 3.5},
        ),
        sample_workspace,
    )

    runs = read_experiment_runs(sample_workspace)
    comparison = compare_experiment_runs("run-a", "run-b", sample_workspace)

    assert [run.run_id for run in runs] == ["run-a", "run-b"]
    assert comparison["metrics"]["return_pct"]["delta"] == 2.5


def test_experiment_artifacts_and_trace(sample_workspace: Path) -> None:
    artifact_path = sample_workspace / "reports" / "research" / "unit.json"
    write_json(artifact_path, {"status": "ok"})
    append_experiment_run(
        ExperimentRun(
            run_id="run-trace",
            name="Trace",
            kind="factor_lab_v2",
            strategy_name="fixture",
            status="ok",
            gate_status="ok",
            artifact_refs=[
                artifact_ref(
                    artifact_path,
                    root=sample_workspace,
                    kind="json",
                    producer="unit_test",
                )
            ],
        ),
        sample_workspace,
    )

    refs = experiment_artifacts("run-trace", sample_workspace)
    trace = trace_experiment_runs("fixture", sample_workspace)

    assert refs[0].path == "reports/research/unit.json"
    assert refs[0].sha256 is not None
    assert [run.run_id for run in trace] == ["run-trace"]
