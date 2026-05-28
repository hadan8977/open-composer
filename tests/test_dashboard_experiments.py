from __future__ import annotations

from pathlib import Path

from open_composer.dashboard import build_dashboard_catalog
from open_composer.experiments import append_experiment_run, artifact_ref
from open_composer.models.experiment import ExperimentRun
from open_composer.storage import write_json


def test_dashboard_reads_experiment_index(sample_workspace: Path) -> None:
    artifact_path = sample_workspace / "reports" / "research" / "experiment-report.json"
    write_json(artifact_path, {"status": "warning"})
    append_experiment_run(
        ExperimentRun(
            run_id="exp-fixture-001",
            name="Fixture experiment",
            research_mode="playground",
            kind="parameter_sweep",
            strategy_name="fixture_pullback_15m",
            source_spec_path="strategy_specs/drafts/fixture_pullback_15m.yaml",
            status="warning",
            gate_status="warning",
            metrics={"candidate_count": 7},
            warning_reasons=["playground_reference_only"],
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

    catalog = build_dashboard_catalog(sample_workspace)

    run = next(item for item in catalog.research_runs if item.run_id == "exp-fixture-001")
    assert run.research_mode == "playground"
    assert run.candidate_count == 7
    assert run.artifact_count == 1
    assert run.warning_items == ["playground_reference_only"]
    assert "warning_items" in run.next_action
