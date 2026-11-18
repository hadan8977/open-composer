"""One explicit same-day recovery after the retained interpreter exec failure.

No source/prepare replay, broker client, fit, timer or automatic retry. Original
source, preparation, failure and formation bytes remain immutable. New outputs
are appended under the received dated input prefix; attempt logs are separate.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_dated_refresh as worker  # noqa: E402
from paper_target_input_controls import receive_current_paper_maintenance  # noqa: E402


def receive_inputs(path, *, now):
    manifest = json.loads(Path(path).read_text())
    assert manifest["purpose"] == "same_day_exec127_saved_stage_recovery_v1"
    root = Path(manifest["prepared_root"]).resolve()
    assert root == worker.RUNS / now.date().isoformat()
    receive_current_paper_maintenance()
    source = worker.receive_source_inventory(root, now=now)
    worker.receive_clock(source["application_day"], source["reference_day"], now=now)
    rows = manifest["immutable_inputs"]
    assert len({r["path"] for r in rows}) == len(rows)
    for row in rows:
        assert worker.binding(row["path"]) == row, "Changed received input/code/runtime"
    paths = {Path(r["path"]) for r in rows}
    required = {
        root / n
        for n in [
            "refresh-start.json",
            "refresh-exit.json",
            "current-source.json",
            "preparation-result.json",
            "prepare-dependencies.json",
            "current-actions.json",
            "action-lineage-QA.json",
            "current-h5-support.json",
            "current-constituents.json",
            "current-marks.json",
            "current-lstm-sequence.npz",
            "lstm-input-QA.json",
            "lstm-prior-prefix-QA.json",
            "targets/BASE.json",
        ]
    }
    assert required <= paths
    names = {
        "run_dated_refresh.py",
        "produce_targets.py",
        "formation_continuity.py",
        "paper_target_input_controls.py",
        "lstm_infer.py",
        "recover_dated_refresh.py",
    }
    assert set(manifest["implementation"]) == names
    for name, identity in manifest["implementation"].items():
        actual = worker.binding(HERE / name)
        assert {k: actual[k] for k in ["bytes", "sha256"]} == identity
    assert Path("/usr/bin/python3.12") in paths
    assert manifest["runtime"]["executable"] == "/usr/bin/python3.12"
    assert manifest["runtime"]["torch_version"] == "2.13.0+cu130"
    failed = json.loads((root / "refresh-exit.json").read_text())
    assert failed["status"] == "blocked_preserved_no_replay"
    assert failed["targets_published"] is False and failed["model_fits"] == 0
    assert [(r["phase"], r["exit_code"]) for r in failed["stages"]] == [
        ("source", 0),
        ("prepare", 0),
        ("inference", 127),
    ]
    for stage in failed["stages"]:
        assert worker.binding(stage["profile"]["path"]) == stage["profile"]
        assert worker.binding(stage["log"]["path"]) == stage["log"]
    preparation = json.loads((root / "preparation-result.json").read_text())
    assert preparation["source"] == worker.binding(root / "current-source.json")
    assert preparation["reference_day"] == source["reference_day"]
    assert preparation["application_day"] == source["application_day"]
    assert preparation["new_fits"] == 0
    return manifest, root, source


def postprocess(path, record):
    """Receive the genuine missed formation; use current prepared unit controls."""
    manifest, root, source = receive_inputs(path, now=datetime.now(UTC))
    claim = json.loads((root / "runtime-recovery-claim.json").read_text())
    assert claim["record"] == str(record.resolve())
    assert claim["manifest"] == worker.binding(path)
    assert claim["worker"] == worker.binding(__file__)
    import produce_targets as producer
    from formation_continuity import FormationDependency, origin, phase, receive_previous, require
    from paper_target_input_controls import receive_action_lineage

    receive_action_lineage(root)
    children = producer.load(root / "current-constituents.json")
    blocked = producer.load(root / "prepare-dependencies.json")
    assert set(children) == {"S1", "S2", "S3", "C2", "BASE"}
    assert set(blocked) == {"H5", "BASE_STATE_BUDGET"}
    try:
        row, signal, observed = origin(manifest["saved_formation"])
        assert row in manifest["immutable_inputs"]
        ref, app = source["reference_day"], source["application_day"]
        require(observed == phase(ref)["latest"] < ref, "Not the genuine held formation")
        assert signal["signal_application"] < app
        support = producer.load(root / "current-h5-support.json")
        assert support["reference_day"] == ref and support["application_day"] == app
        assert support["source"] == worker.binding(root / "current-source.json")
        previous = receive_previous()
        assert support["symbols"] == previous["symbols"] == signal["symbols"]
        weights = signal["allocation"]["weights"]
        require(
            len(weights) == len(support["current_eligible"]) == 32,
            "Incomplete held formation/current support",
        )
        require(
            all(yes for yes, w in zip(support["current_eligible"], weights, strict=True) if w > 0),
            "Held H5 lacks current unit/action support",
        )
    except (FormationDependency, AssertionError, FileNotFoundError) as error:
        # A missing held formation blocks its dependent policies, not the
        # independently received BASE/current recurrent inference.
        worker.save(
            record / "formation-dependency.json",
            dict(
                reason=str(error),
                original_dependencies=worker.binding(root / "prepare-dependencies.json"),
            ),
        )
        producer.assemble(root)
        producer.finish(root)
        return
    marks = producer.load(root / "current-marks.json")
    carriers = previous["controls"]["carriers"]
    predecessor = record / "predecessor-instructions"
    predecessor.mkdir(exist_ok=False)
    old_instruction = worker.TARGETS / "H5.json"
    old_body = old_instruction.read_bytes()
    assert worker.binding(old_instruction) in manifest["immutable_inputs"]
    with (predecessor / "H5.json").open("xb") as stream:
        stream.write(old_body)
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(predecessor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    h5 = producer.target(
        root,
        "H5",
        [carriers.get(s) or s for s in support["symbols"]],
        weights,
        marks,
        source,
        ref,
        app,
        signal_forecast=row,
        signal_observation=observed,
        signal_application=signal["signal_application"],
        original_computed_at=signal["computed_completed_at"],
        next_regular_observation=phase(ref)["next_observation"],
        next_regular_application=phase(ref)["next_application"],
        model_epoch="2026-10",
        is_fresh_prediction=False,
        received_unadopted_formation=worker.binding(predecessor / "H5.json"),
        K=signal["allocation"]["K"],
        allocation_intent="complete_unfulfilled_initial_allocation_only_after_operating_prefix_acceptance",
    )
    base = producer.load(root / "targets/BASE.json")
    assert children["BASE"] == dict(base, name="BASE")
    oldbase = producer.load(producer.T / "inference/BASE/output.json")
    base_weights = dict(zip(base["symbols"], base["weights"], strict=True))
    assert set(base_weights) <= set(oldbase["symbols"])
    producer.target(
        root,
        "BASE_STATE_BUDGET",
        oldbase["symbols"],
        [base_weights.get(s, 0.0) * h5["K"] / 5 for s in oldbase["symbols"]],
        marks,
        source,
        ref,
        app,
        K=h5["K"],
        duplicates_BASE_now=h5["K"] == 5,
        held_model_origins=[base["held_model_origin"], h5["signal_forecast"]],
        causal_inputs=dict(
            BASE=worker.binding(root / "targets/BASE.json"),
            H5=worker.binding(root / "targets/H5.json"),
        ),
        cash_cause="causal_H5_K_scaling_of_current_BASE",
        allocation_intent="complete_unfulfilled_initial_allocation_only_after_operating_prefix_acceptance",
    )
    children["H5"] = dict(h5, name="H5")
    worker.save(
        record / "received-formation.json",
        dict(
            original_dependencies=worker.binding(root / "prepare-dependencies.json"),
            origin=row,
            current_support=worker.binding(root / "current-h5-support.json"),
            historical_signal_dates_preserved=True,
            fresh_H5_forward_calls=0,
        ),
    )
    producer.assemble(root, received_children=children)
    producer.finish(root, received_prepare_dependencies={})


def run_stage(name, cap, command, record, application_day):
    receive_current_paper_maintenance()
    worker.receive_clock(application_day)
    admission = subprocess.run(
        [
            sys.executable,
            str(worker.REPO / "scripts/memory_budget.py"),
            "admit",
            "--kind",
            "job",
            "--class",
            "research",
            "--mem",
            str(cap),
        ],
        cwd=worker.REPO,
        capture_output=True,
        text=True,
    )
    worker.save(
        record / (name + "-admission.json"),
        dict(returncode=admission.returncode, stdout=admission.stdout, stderr=admission.stderr),
    )
    assert admission.returncode == 0, "Actual memory admission refused"
    receive_current_paper_maintenance()
    worker.receive_clock(application_day)
    wrapper = [
        str(worker.REPO / "scripts/run_capped.sh"),
        "--class",
        "paper",
        "--mem",
        str(cap) + "M",
        "--swap",
        "0",
        "--",
        "/usr/bin/time",
        "-v",
        "-o",
        str(record / (name + ".profile")),
        "timeout",
        "1200",
        "taskset",
        "-c",
        "0",
        "env",
        "PYTHONDONTWRITEBYTECODE=1",
        "OMP_NUM_THREADS=1",
        "OPENBLAS_NUM_THREADS=1",
        "MKL_NUM_THREADS=1",
    ]
    with (record / (name + ".log")).open("xb") as log:
        completed = subprocess.run(
            wrapper + command, cwd=worker.REPO, stdout=log, stderr=subprocess.STDOUT
        )
    row = dict(
        phase=name,
        exit_code=completed.returncode,
        profile=worker.binding(record / (name + ".profile")),
        log=worker.binding(record / (name + ".log")),
    )
    worker.save(record / (name + "-exit.json"), row)
    assert completed.returncode == 0, "Recovery stage failed; preserve, no automatic retry"
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--postprocess", action="store_true")
    args = parser.parse_args()
    record = args.record.resolve()
    assert record.is_relative_to(worker.REPO / "reports/paper/diagnostics")
    if args.postprocess:
        assert not args.publish
        postprocess(args.manifest, record)
        return 0
    manifest, root, source = receive_inputs(args.manifest, now=datetime.now(UTC))
    assert not (root / "current-lstm-inference.json").exists(), "No completed forward replay"
    record.mkdir(parents=True, exist_ok=False)
    worker.save(
        root / "runtime-recovery-claim.json",
        dict(
            record=str(record),
            manifest=worker.binding(args.manifest),
            worker=worker.binding(__file__),
            at=datetime.now(UTC).isoformat(),
        ),
    )
    result = dict(
        source_GETs=0,
        prepare_replays=0,
        model_fits=0,
        broker_calls=0,
        targets_published=False,
        stages=[],
    )
    status = 1
    try:
        inference = next(
            c for c in worker.commands(root, source["application_day"]) if c[0] == "inference"
        )
        result["stages"].append(run_stage(*inference, record, source["application_day"]))
        received = json.loads((root / "current-lstm-inference.json").read_text())
        assert received["torch_version"] == manifest["runtime"]["torch_version"]
        assert received["new_fits"] == 0 and received["new_inferences"] == 2
        assert (
            received["source_sequence_sha256"]
            == worker.binding(root / "current-lstm-sequence.npz")["sha256"]
        )
        result["stages"].append(
            run_stage(
                "postprocess",
                600,
                [
                    sys.executable,
                    str(HERE / "recover_dated_refresh.py"),
                    "--manifest",
                    str(args.manifest.resolve()),
                    "--record",
                    str(record),
                    "--postprocess",
                ],
                record,
                source["application_day"],
            )
        )
        worker.receive_packet(root, now=datetime.now(UTC))
        result.update(
            status="complete_current_staging_recovery",
            target_result=worker.binding(root / "target-production-result.json"),
        )
        if args.publish:
            result.update(
                published=worker.publish_packet(root, now=datetime.now(UTC)),
                targets_published=True,
                status=(
                    "partial_current_input_recovery_published"
                    if json.loads((root / "target-production-result.json").read_text())[
                        "blocked_policies"
                    ]
                    else "current_input_recovery_published"
                ),
            )
        status = 0
    except Exception as error:
        result.update(
            status="blocked_recovery_preserved", error_type=type(error).__name__, error=str(error)
        )
    finally:
        result.update(exit_code=status, at=datetime.now(UTC).isoformat())
        worker.save(record / "recovery-exit.json", result)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
