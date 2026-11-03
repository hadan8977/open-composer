"""The original November H5 fold and two fixed estimators; finite, no broker I/O.

The October initialization deadline is not reused as a November receipt clock.
New states retain their real source, preparation and fit timestamps. Daily
formation can only use this pair at a genuine November observation; held October
signals continue to receive their own original October states.
"""

import argparse
import ast
import gzip
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from open_composer.paper_runtime.six import formation_continuity as f
from open_composer.paper_runtime.source_loader import source_bytes

EPOCH = "2026-11"
CUTOFF = "2026-10-30"
FIRST_OBSERVATION = "2026-11-06"
POINTER = Path("runtime/paper/six/monthly-h5-2026-11.json")
DESTINATION = Path("reports/paper/diagnostics/h5-monthly-20261103/models")
LEARNING_SHA = "680feb717363c8ca36e87777a164534c2433bd6ec46630e2edb53c1f2bcd67f7"
PACKET_SHA = "c52f75111c91e4c16d000662197172dbc26858893a4e1cd9a5c8fb57acab1733"
TRAINING_AUDIT_SHA = "d6e339cd99f2281a0b05ca81a3b9b6690d1fbef35cef94bb5c44f1e712f539cb"


def now():
    return datetime.now(UTC).isoformat()


def digest(value):
    return hashlib.sha256(value.tobytes()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, allow_nan=False, indent=2)
        stream.write("\n")
    return f.binding(path)


def impute(train, test, state_arm):
    """Execute only the unchanged accepted pure training imputer."""
    import numpy as np

    path = f.STUDY / "learning.py"
    body = source_bytes(path, root=f.REPO)
    assert hashlib.sha256(body).hexdigest() == LEARNING_SHA
    nodes = [
        n
        for n in ast.parse(body).body
        if isinstance(n, ast.FunctionDef) and n.name == "impute_training"
    ]
    assert len(nodes) == 1
    namespace = dict(np=np, STOCK=list(range(9)))
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), "exec"
        ),
        namespace,
    )
    return namespace["impute_training"](train, test, state_arm=state_arm)


def feature_orders():
    # Read the accepted original feature-name constants without running its study.
    body = source_bytes(f.STUDY / "method.py", root=f.REPO)
    constants = [
        n
        for n in ast.parse(body).body
        if isinstance(n, ast.Assign)
        and any(
            isinstance(t, ast.Name) and t.id in ["STOCK", "STATE", "INTERACTIONS"]
            for t in n.targets
        )
    ]
    namespace = {}
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=constants, type_ignores=[])),
            str(f.STUDY / "method.py"),
            "exec",
        ),
        namespace,
    )
    stock = namespace["STOCK"]
    state = namespace["STATE"] + namespace["INTERACTIONS"]
    return dict(STOCK=stock, STATE=stock + state + ["missing_" + n for n in state])


def material(packet_dir):
    """Recompute the exact original fold/imputation and immutable-prefix checks."""
    import numpy as np

    packet_dir = Path(packet_dir)
    assert f.binding(packet_dir / "audit.json")["sha256"] == PACKET_SHA
    audit = f.load(packet_dir / "audit.json")
    assert audit["epoch"] == EPOCH and audit["cutoff"] == CUTOFF
    for name, row in audit["outputs"].items():
        assert Path(row["path"]) == packet_dir / name
        f.checked(row)
    with np.load(f.checked(audit["outputs"]["prepared.npz"]), allow_pickle=False) as archive:
        data = {k: archive[k] for k in archive.files}
    with np.load(f.checked(audit["accepted_prepared"]), allow_pickle=False) as archive:
        old = {k: archive[k] for k in archive.files}
    n = len(old["dates"])
    assert old["dates"][-1] == "2026-09-30" and data["dates"][-1] == CUTOFF
    assert data["episodes"].tobytes() == old["episodes"].tobytes()
    for name in [
        "stock",
        "state",
        "raw_state",
        "eligible",
        "state_missing",
        "eligible_count",
        "dates",
        "returns",
        "available",
        "benchmark_SPY",
        "maturity",
    ]:
        assert data[name][:n].tobytes() == old[name].tobytes(), "Changed original prefix: " + name
    finite = np.isfinite(old["labels"])
    assert data["labels"][:n][finite].tobytes() == old["labels"][finite].tobytes()
    changed = ~np.isfinite(old["labels"]) & np.isfinite(data["labels"][:n])
    allowed = (old["label_status"] == 2) & old["eligible"]
    assert not np.any(changed & ~allowed)
    label_fn = f.pure("features", "fixed_labels", np=np)
    full = label_fn(data["returns"], data["eligible"])
    expected_labels = old["labels"].copy()
    mature = allowed & np.isfinite(full["labels"][:n])
    expected_labels[mature] = full["labels"][:n][mature]
    expected_status = old["label_status"].copy()
    expected_status[mature] = 1
    assert np.array_equal(data["labels"][:n], expected_labels, equal_nan=True)
    assert np.array_equal(data["label_status"][:n], expected_status)
    for name in ["labels", "label_status", "maturity"]:
        assert np.array_equal(data[name][n:], full[name][n:], equal_nan=True)
    cutoff = len(data["dates"]) - 1
    calendar = np.arange(cutoff + 1)[-756:]
    calendar = calendar[data["dates"][calendar] >= "2021-01-04"]
    available_dates = calendar[data["maturity"][calendar] <= cutoff]
    ii, jj = np.where(
        data["eligible"][available_dates] & np.isfinite(data["labels"][available_dates])
    )
    td = available_dates[ii]
    weights = 1 / np.bincount(td, minlength=len(data["dates"]))[td]
    assert len(td) >= 5000 and len(np.unique(td)) >= 252 and len(np.unique(jj)) >= 20
    with np.load(f.checked(audit["outputs"]["training.npz"]), allow_pickle=False) as received:
        for name, expected in dict(
            train_d=td, train_j=jj, weights=weights, calendar=calendar, cutoff=np.asarray(cutoff)
        ).items():
            assert received[name].tobytes() == expected.tobytes()
    target = data["labels"][td, jj]
    orders, matrices, preprocessing = feature_orders(), {}, {}
    for arm, width in [("STOCK", 9), ("STATE", 33)]:
        raw = data[arm.lower()][td, jj]
        train, _, medians = impute(raw, raw[:0], arm == "STATE")
        assert train.shape == (len(td), width) and np.isfinite(train).all()
        matrices[arm] = train
        preprocessing[arm] = dict(
            feature_order=orders[arm],
            medians=medians.tolist(),
            medians_sha256=digest(medians),
            raw_matrix_sha256=digest(raw),
            train_matrix_sha256=digest(train),
            width=width,
        )
    return audit, data, old, td, jj, weights, target, matrices, preprocessing


def audit_packet(packet_dir):
    """Save actual per-date maturation, selected IDs/weights and 9/33-column audit."""
    import numpy as np

    audit, data, old, td, jj, weights, target, _, prep = material(packet_dir)
    n = len(old["dates"])

    def status_row(d):
        original = old["label_status"][d] if d < n else None
        current = data["label_status"][d]
        return dict(
            day=str(data["dates"][d]),
            original_status_counts=None
            if original is None
            else {str(k): int(np.sum(original == k)) for k in range(4)},
            current_status_counts={str(k): int(np.sum(current == k)) for k in range(4)},
            newly_mature=int(np.sum((original == 2) & (current == 1)))
            if original is not None
            else int(np.sum(current == 1)),
            still_unknown_eligible=int(
                np.sum(data["eligible"][d] & ~np.isfinite(data["labels"][d]))
            ),
        )

    result = dict(
        epoch=EPOCH,
        cutoff=CUTOFF,
        audited_at=now(),
        packet=f.binding(Path(packet_dir) / "audit.json"),
        preprocessing=prep,
        labels_sha256=digest(target),
        ID_weight_sha256=hashlib.sha256(
            np.column_stack([td, jj]).tobytes() + weights.tobytes()
        ).hexdigest(),
        rows=len(td),
        dates=len(np.unique(td)),
        episodes=len(np.unique(jj)),
        first_training_day=str(data["dates"][td.min()]),
        last_training_day=str(data["dates"][td.max()]),
        latest_maturity_endpoint=str(data["dates"][data["maturity"][td].max()]),
        date_weight_sums=[
            dict(
                day=str(data["dates"][d]),
                rows=int(np.sum(td == d)),
                weight=float(weights[td == d].sum()),
            )
            for d in np.unique(td)
        ],
        September_tail=[status_row(d) for d in range(n - 6, n)],
        October=[status_row(d) for d in range(n, len(data["dates"]))],
        bitexact_old_arrays=True,
        finite_old_labels_bitexact=True,
        only_original_status2_can_mature=True,
        frozen_sources=dict(learning_sha256=LEARNING_SHA, method_sha256=f.ORIGINALS["features"][1]),
        fits=0,
        HTTP=0,
    )
    assert result["ID_weight_sha256"] == audit["ID_weight_sha256"]
    return save(Path(packet_dir) / "training-audit.json", result)


def receive_input(packet_dir):
    packet_dir = Path(packet_dir)
    audit, *_, prep = material(packet_dir)
    training = f.load(packet_dir / "training-audit.json")
    assert f.binding(packet_dir / "training-audit.json")["sha256"] == TRAINING_AUDIT_SHA
    assert training["packet"] == f.binding(packet_dir / "audit.json")
    assert training["preprocessing"] == prep
    assert training["ID_weight_sha256"] == audit["ID_weight_sha256"]
    assert audit["fit_calls"] == audit["HTTP_calls"] == audit["production_writes"] == 0
    return audit, training


def fit_models(packet_dir, output_dir):
    """Exactly the two original fixed fits, one exclusive attempt, then exit."""
    from open_composer.research.ml_backend.model_factory import create_model

    packet_dir, output_dir = Path(packet_dir), Path(output_dir)
    assert not output_dir.exists(), (
        "Retain partial/failed fits; never retry over an existing attempt"
    )
    output_dir.mkdir(parents=True)
    started = now()
    save(
        output_dir / "started.json",
        dict(
            started_at=started,
            packet=f.binding(packet_dir / "audit.json"),
            training=f.binding(packet_dir / "training-audit.json"),
        ),
    )
    audit, training = receive_input(packet_dir)
    _, _, _, _, _, weight, target, matrices, prep = material(packet_dir)
    parameters = f.load(f.H5 / "prospective-contract.json")["models"]
    rows = []
    for arm in ["STOCK", "STATE"]:
        context = dict(
            arm=arm,
            epoch=EPOCH,
            cutoff=CUTOFF,
            first_observation=FIRST_OBSERVATION,
            input=f.binding(packet_dir / "audit.json"),
            training=f.binding(packet_dir / "training-audit.json"),
            parameters=parameters,
            feature_order=prep[arm]["feature_order"],
            medians=prep[arm]["medians"],
            preprocessing=prep[arm],
            rows=training["rows"],
            labels_sha256=training["labels_sha256"],
            ID_weight_sha256=training["ID_weight_sha256"],
            model_attempt=str(output_dir.resolve()) + ":" + arm,
            started_at=now(),
        )
        started_row = save(output_dir / (arm + "-started.json"), context)
        model = create_model(
            SimpleNamespace(
                model=SimpleNamespace(
                    kind="lightgbm_regressor",
                    hyperparameters=parameters,
                    training=SimpleNamespace(seed=20261016),
                )
            )
        )
        model.fit(matrices[arm], target, sample_weight=weight)
        state = dict(
            context=context,
            model_string=model.booster_.model_to_string(),
            tree_dump=model.booster_.dump_model(),
            fitted_at=now(),
            actual_params=model.get_params(),
        )
        path = output_dir / (arm + ".json.gz")
        with path.open("xb") as stream:
            stream.write(
                gzip.compress(
                    json.dumps(state, allow_nan=False, separators=(",", ":")).encode(), mtime=0
                )
            )
        rows.append(dict(arm=arm, state=f.binding(path), started=started_row, completed_at=now()))
        del model
    result = dict(
        epoch=EPOCH,
        cutoff=CUTOFF,
        first_observation=FIRST_OBSERVATION,
        last_observation="2026-11-30",
        first_application="2026-11-09",
        models=rows,
        input=f.binding(packet_dir / "audit.json"),
        training=f.binding(packet_dir / "training-audit.json"),
        contract=f.binding(f.H5 / "prospective-contract.json"),
        source=audit["source"],
        source_captured_at=audit["source_captured_at"],
        input_prepared_at=audit["prepared_at"],
        started_at=started,
        completed_at=now(),
        genuine_new_fits=2,
        current_predictions=0,
    )
    row = save(output_dir / "models.json", result)
    receive_models(row)
    return row


def receive_models(receipt):
    """Read-only exact pair/parameter/preprocessing/time reception; no estimator."""
    result = f.load(f.checked(receipt))
    assert result["epoch"] == EPOCH and result["cutoff"] == CUTOFF
    assert (
        result["first_observation"] == FIRST_OBSERVATION
        and result["last_observation"] == "2026-11-30"
    )
    assert result["genuine_new_fits"] == 2 and result["current_predictions"] == 0
    assert result["input"]["sha256"] == PACKET_SHA
    assert result["training"]["sha256"] == TRAINING_AUDIT_SHA
    training = f.load(f.checked(result["training"]))
    packet = f.load(f.checked(result["input"]))
    assert (
        training["packet"] == result["input"]
        and training["ID_weight_sha256"] == packet["ID_weight_sha256"]
    )
    for row in packet["outputs"].values():
        f.checked(row)
    f.checked(packet["accepted_prepared"])
    f.checked(packet["amendment"])
    assert result["contract"] == f.binding(f.H5 / "prospective-contract.json")
    parameters = f.load(f.checked(result["contract"]))["models"]
    assert result["source"] == packet["source"]
    f.checked(result["source"])
    assert (
        datetime.fromisoformat(result["source_captured_at"])
        <= datetime.fromisoformat(result["input_prepared_at"])
        <= datetime.fromisoformat(result["started_at"])
    )
    orders, states = feature_orders(), {}
    assert [r["arm"] for r in result["models"]] == ["STOCK", "STATE"]
    for row in result["models"]:
        arm = row["arm"]
        state = json.loads(gzip.decompress(f.checked(row["state"]).read_bytes()))
        context = state["context"]
        assert context == f.load(f.checked(row["started"]))
        assert context["arm"] == arm and context["epoch"] == EPOCH and context["cutoff"] == CUTOFF
        assert context["input"] == result["input"] and context["training"] == result["training"]
        assert context["preprocessing"] == training["preprocessing"][arm]
        assert context["feature_order"] == orders[arm] == context["preprocessing"]["feature_order"]
        assert context["medians"] == context["preprocessing"]["medians"]
        assert (
            context["rows"] == training["rows"]
            and context["labels_sha256"] == training["labels_sha256"]
        )
        assert context["ID_weight_sha256"] == training["ID_weight_sha256"]
        assert context["parameters"] == parameters and all(
            state["actual_params"][k] == v for k, v in parameters.items()
        )
        assert (
            datetime.fromisoformat(result["started_at"])
            <= datetime.fromisoformat(context["started_at"])
            <= datetime.fromisoformat(state["fitted_at"])
            <= datetime.fromisoformat(row["completed_at"])
            <= datetime.fromisoformat(result["completed_at"])
        )
        assert state["tree_dump"]["average_output"] is False
        states[arm] = state
    assert len({s["context"]["model_attempt"] for s in states.values()}) == 2
    return result, states


def install(receipt, *, root):
    """Copy the received pair to stable MAIN evidence, then create its fixed pointer."""
    result, _ = receive_models(receipt)
    destination = Path(root) / DESTINATION
    pointer = Path(root) / POINTER
    assert not destination.exists() and not pointer.exists(), "Never replace an installed month"
    destination.mkdir(parents=True)
    installed = []
    for row in result["models"]:
        new_row = dict(row)
        for key in ["state", "started"]:
            source = f.checked(row[key])
            target = destination / source.name
            shutil.copyfile(source, target)
            new_row[key] = f.binding(target)
            assert {k: new_row[key][k] for k in ["sha256", "bytes"]} == {
                k: row[key][k] for k in ["sha256", "bytes"]
            }
        installed.append(new_row)
    stable = save(
        destination / "models.json",
        dict(result, models=installed, original_receipt=receipt, installed_at=now()),
    )
    receive_models(stable)
    return save(
        pointer, dict(epoch=EPOCH, receipt=stable, original_receipt=receipt, installed_at=now())
    )


def current(observation, *, root=None):
    """Find the actual received November pair; dates never select October as fallback."""
    root = f.REPO if root is None else Path(root)
    assert FIRST_OBSERVATION <= observation <= "2026-11-30", "Unreceived H5 observation month"
    pointer = f.load(root / POINTER)
    assert pointer["epoch"] == EPOCH
    receipt = pointer["receipt"]
    assert Path(receipt["path"]) == root / DESTINATION / "models.json"
    result, states = receive_models(receipt)
    return receipt, result, states


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    audit = sub.add_parser("audit")
    audit.add_argument("packet", type=Path)
    fit = sub.add_parser("fit")
    fit.add_argument("packet", type=Path)
    fit.add_argument("output", type=Path)
    receive = sub.add_parser("receive")
    receive.add_argument("receipt", type=Path)
    install_parser = sub.add_parser("install")
    install_parser.add_argument("receipt", type=Path)
    install_parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    if args.operation == "audit":
        result = audit_packet(args.packet)
    elif args.operation == "fit":
        result = fit_models(args.packet, args.output)
    elif args.operation == "install":
        result = install(f.binding(args.receipt), root=args.root)
    else:
        value, _ = receive_models(f.binding(args.receipt))
        result = dict(
            received=True,
            epoch=value["epoch"],
            fits=value["genuine_new_fits"],
            completed_at=value["completed_at"],
        )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
