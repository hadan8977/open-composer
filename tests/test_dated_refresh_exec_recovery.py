"""Focused saved/private checks; never invokes a client, source or model."""

import ast
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from open_composer.paper_runtime.six import recover_dated_refresh as recovery
from open_composer.paper_runtime.source_loader import source_bytes

HERE = Path(recovery.__file__).parent
FROZEN_NOW = datetime(2026, 10, 27, 3, tzinfo=UTC)

EVIDENCE = Path(
    "/root/codex-test/open-composer/reports/paper/diagnostics/inference-runtime-repair-20261027"
)


def test_historical_recovery_manifest_does_not_authorize_migrated_code():
    manifest = json.loads((EVIDENCE / "recovery-inputs.json").read_text())
    assert manifest["runtime"]["executable"] == "/usr/bin/python3.12"
    changed = [
        row for row in manifest["immutable_inputs"] if recovery.worker.binding(row["path"]) != row
    ]
    assert changed  # This retained receipt already predates further source maintenance.
    # A source/code migration does not turn an old recovery receipt into authority.
    with pytest.raises(AssertionError):
        recovery.receive_inputs(EVIDENCE / "recovery-inputs.json", now=FROZEN_NOW)
    assert (
        recovery.worker.commands(Path(manifest["prepared_root"]), "2026-10-27")[2][2][0]
        == "/usr/bin/python3.12"
    )


def test_changed_input_and_wrong_day_refuse(tmp_path):
    data = json.loads((EVIDENCE / "recovery-inputs.json").read_text())
    data["immutable_inputs"][0]["sha256"] = "0" * 64
    p = tmp_path / "changed.json"
    p.write_text(json.dumps(data))
    with pytest.raises(AssertionError, match="Changed received input"):
        recovery.receive_inputs(p, now=FROZEN_NOW)
    with pytest.raises(AssertionError):
        recovery.receive_inputs(
            EVIDENCE / "recovery-inputs.json", now=datetime(2026, 10, 28, 2, tzinfo=UTC)
        )


def test_no_new_scientific_body():
    old = ast.parse((EVIDENCE / "produce_targets.py").read_text())
    new = ast.parse(
        source_bytes("reports/research/program/paper-launch-20min-20261021/produce_targets.py")
    )
    # Only optional received prepared children/dependencies change. No numerical
    # preparation, target semantics, ETF/calendar or recurrent body changes.
    for name in ["prepare", "prepare_core", "target", "dated", "session_clocks"]:
        a = next(n for n in old.body if isinstance(n, ast.FunctionDef) and n.name == name)
        b = next(n for n in new.body if isinstance(n, ast.FunctionDef) and n.name == name)
        assert ast.dump(a) == ast.dump(b)
    assert (
        source_bytes("reports/research/program/paper-launch-20min-20261021/lstm_infer.py")
        == (EVIDENCE / "lstm_infer.py").read_bytes()
    )


def test_private_held_formation_and_missing_support(tmp_path):
    root = tmp_path / "prepared"
    root.mkdir()
    record = tmp_path / "record"
    record.mkdir()
    manifest_path = tmp_path / "manifest"
    manifest_path.write_text("{}")
    row = {"path": "immutable-Oct23-formation", "sha256": "original"}
    base = dict(symbols=["A"], weights=[0.75], held_model_origin={"sha256": "BASE"})
    children = {n: {"name": n} for n in ["S1", "S2", "S3", "C2"]}
    children["BASE"] = dict(base, name="BASE")
    source = dict(reference_day="2026-10-26", application_day="2026-10-27")
    support = dict(
        reference_day=source["reference_day"],
        application_day=source["application_day"],
        source=recovery.worker.binding(manifest_path),
        symbols=[str(i) for i in range(32)],
        current_eligible=[True] * 32,
    )
    signal = dict(
        symbols=support["symbols"],
        allocation=dict(weights=[1.0] + [0.0] * 31, K=5),
        signal_application="2026-10-26",
        computed_completed_at="2026-10-26T00:20:30Z",
    )
    manifest = dict(saved_formation=row, immutable_inputs=[row])
    files = {
        "current-constituents.json": children,
        "prepare-dependencies.json": {"H5": "missed", "BASE_STATE_BUDGET": "missing H5"},
        "current-h5-support.json": support,
        "current-marks.json": {},
        "BASE.json": base,
        "output.json": {"symbols": ["A", "B"]},
    }
    outputs = []

    def target(root, policy, symbols, weights, *args, **kwargs):
        kwargs.setdefault("portfolio_action", "rebalance")
        value = dict(policy=policy, symbols=symbols, weights=weights, **kwargs)
        outputs.append(value)
        return value

    producer = SimpleNamespace(
        load=lambda p: json.loads(json.dumps(files[p.name])),
        T=tmp_path,
        target=target,
        assemble=lambda root, **kw: outputs.append(kw),
        finish=lambda root, **kw: outputs.append(kw),
    )
    formation = SimpleNamespace(
        FormationDependency=ValueError,
        origin=lambda r: (row, signal, "2026-10-23"),
        phase=lambda ref: dict(
            latest="2026-10-23", next_observation="2026-10-30", next_application="2026-11-02"
        ),
        receive_previous=lambda: dict(symbols=support["symbols"], controls={"carriers": {}}),
        require=lambda yes, msg: None if yes else (_ for _ in ()).throw(ValueError(msg)),
    )
    private_targets = tmp_path / "live-targets"
    private_targets.mkdir()
    (private_targets / "H5.json").write_text('{"policy":"H5"}')
    fixed_binding = recovery.worker.binding(manifest_path)
    manifest["immutable_inputs"].append(fixed_binding)

    def binding(p):
        return fixed_binding

    claim = root / "runtime-recovery-claim.json"
    claim.write_text(
        json.dumps(
            dict(
                record=str(record.resolve()),
                manifest=binding(manifest_path),
                worker=binding(recovery.__file__),
            )
        )
    )
    with (
        patch.dict(
            sys.modules,
            {
                "open_composer.paper_runtime.six.produce_targets": producer,
                "open_composer.paper_runtime.six.formation_continuity": formation,
            },
        ),
        patch("open_composer.paper_runtime.six.produce_targets", producer),
        patch.object(recovery, "receive_inputs", return_value=(manifest, root, source)),
        patch.object(recovery.worker, "binding", side_effect=binding),
        patch.object(recovery.worker, "TARGETS", private_targets),
        patch(
            "open_composer.paper_runtime.six.paper_target_input_controls.receive_action_lineage",
            return_value=None,
        ),
    ):
        recovery.postprocess(manifest_path, record)
        h5, state = outputs[:2]
        assert h5["signal_observation"] == "2026-10-23"
        assert h5["signal_application"] == "2026-10-26"
        assert h5["is_fresh_prediction"] is False and h5["portfolio_action"] == "rebalance"
        assert state["weights"] == [0.75, 0.0]
        assert outputs[-1] == {"received_prepare_dependencies": {}}
        support["current_eligible"][0] = False
        outputs.clear()
        recovery.postprocess(manifest_path, record)
        assert outputs == [{}, {}]  # Original dependency maps retained; BASE/LSTM continue.


def test_prospective_saved_formation_action_receiver(tmp_path):
    """Changed never-adopted weights require the original rebalance action."""
    path = tmp_path / "reports/paper/diagnostics/predecessor/H5.json"
    path.parent.mkdir(parents=True)
    prior = dict(policy="H5", symbols=["A"], weights=[1.0], signal_forecast={"old": True})
    path.write_text(json.dumps(prior))
    prior_row = recovery.worker.binding(path)
    signal = dict(
        symbols=["A"], allocation=dict(weights=[0.0], K=0), signal_application="2026-10-26"
    )
    row = dict(path="new-genuine-formation")
    prior_day = ["2026-10-19"]

    def origin(r):
        return (row, signal, "2026-10-23") if r == row else (r, {}, prior_day[0])

    tree = ast.parse((HERE / "formation_continuity.py").read_text())
    node = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "receive_h5_instruction"
    )
    namespace = dict(
        origin=origin,
        phase=lambda ref: {"latest": "2026-10-23"},
        receive_previous=lambda: {"controls": {"carriers": {}}},
        checked=lambda r: Path(r["path"]),
        load=lambda p: json.loads(p.read_text()),
        Path=Path,
        REPO=tmp_path,
    )
    exec(
        compile(ast.Module(body=[node], type_ignores=[]), "private-original-receiver", "exec"),
        namespace,
    )
    target = dict(
        signal_forecast=row,
        signal_observation="2026-10-23",
        reference_day="2026-10-26",
        application_day="2026-10-27",
        signal_application="2026-10-26",
        symbols=[],
        weights=[],
        K=0,
        is_fresh_prediction=False,
        received_unadopted_formation=prior_row,
        prior_target=prior_row,
        weights_unchanged=False,
        portfolio_action="rebalance",
    )
    receive = namespace["receive_h5_instruction"]
    assert receive(tmp_path, target) == row
    with pytest.raises(AssertionError):
        receive(tmp_path, dict(target, portfolio_action="hold"))
    prior_day[0] = "2026-10-23"
    with pytest.raises(AssertionError):
        receive(tmp_path, target)
    prior_day[0] = "2026-10-19"
    with pytest.raises(AssertionError):
        receive(tmp_path, dict(target, prior_target=dict(prior_row, sha256="0" * 64)))
