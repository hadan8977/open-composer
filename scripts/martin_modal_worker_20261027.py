"""Exact Martin runtime proof or missing-root shard on the existing Modal runner."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import resource
import sys
import tarfile
import time
from collections import Counter
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

TASK = "reports/research/program/martin-decision-loop-model-continuation-20261026"
REPO = Path("/root/repo")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def utc():
    return datetime.now(UTC).isoformat()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:
        stream.write(json.dumps(value, default=str, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def append(path, value):
    with Path(path).open("a") as stream:
        stream.write(json.dumps(value, default=str) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


class GrantStopped(RuntimeError):
    pass


class LiveGrant:
    def __init__(self, modal, manifest, digest, key, phase):
        self.control = modal.Dict.from_name(manifest["control_dict"])
        self.manifest_sha, self.key, self.phase = digest, key, phase
        self.last = None

    def gate(self, *, new_start=False, training=False, financial=False):
        assert not training and not financial, "This grant admits no model or account"
        raw = self.control.get(self.key)
        if not isinstance(raw, str):
            raise GrantStopped("Missing live task grant")
        grant = json.loads(raw)
        assert grant["runtime_manifest_sha256"] == self.manifest_sha
        assert grant["job_key"] == self.key and grant["phase"] == self.phase
        assert grant["schema_version"] == 1
        self.last = grant
        if datetime.now(UTC) >= datetime.fromisoformat(grant["expires_at_utc"]):
            raise GrantStopped("Finite task grant expired")
        if not grant["research_allowed"]:
            raise GrantStopped("Actual relayed owner/research stop")
        if new_start and not grant["new_roots_allowed"]:
            raise GrantStopped("Actual relayed new-start checkpoint")

    def claim(self, shard, run_id):
        """Fence platform retries and a second driver independently of RUN_ID."""
        key = f"claim:{self.key}:{self.phase}:{shard}"
        claim = dict(
            job_key=self.key,
            phase=self.phase,
            shard=shard,
            run_id=run_id,
            runtime_manifest_sha256=self.manifest_sha,
            at_utc=utc(),
            function_call_id=os.environ.get("OC_MODAL_FUNCTION_CALL_ID"),
            input_id=os.environ.get("OC_MODAL_INPUT_ID"),
            pid=os.getpid(),
        )
        assert self.control.put(key, json.dumps(claim), skip_if_exists=True), (
            "Partition already claimed: preserve prior durable evidence; no automatic replay"
        )
        assert json.loads(self.control.get(key)) == claim
        return claim


def unpack(manifest):
    archive = REPO / manifest["archive"]["path"]
    assert sha(archive) == manifest["archive"]["sha256"]
    with tarfile.open(archive, "r:gz") as stream:
        for member in stream.getmembers():
            path = Path(member.name)
            assert member.isfile() and not path.is_absolute() and ".." not in path.parts
            assert str(path).startswith("reports/research/program/")
        stream.extractall(REPO, filter="data")
    index = REPO / manifest["payload_index"]["path"]
    assert sha(index) == manifest["payload_index"]["sha256"]
    for row in json.loads(index.read_text())["files"]:
        path = REPO / row["path"]
        assert path.stat().st_size == row["bytes"] and sha(path) == row["sha256"]
    original = Path(manifest["original_source_root"])
    if not original.exists():
        original.parent.mkdir(parents=True, exist_ok=True)
        original.symlink_to(REPO, target_is_directory=True)
    assert original.resolve() == REPO


def raw_semantic_case(case):
    fields = (
        "intent_id",
        "symbol",
        "action",
        "reason",
        "native_ns",
        "quantity",
        "price",
        "fee",
        "cancelled_quantity",
        "actual_cash_before",
        "actual_cash_after",
        "terminal_callback_index",
        "received_mark_valuation_before_callback",
    )
    freshness = (
        "fresh",
        "source_event_ns",
        "source_field",
        "source_price",
        "actual_callback_ns",
        "last_observed_quote_ns",
        "actual_applied_book_ns",
        "own_source_point_actually_applied",
        "current_minute",
        "exact_source_price",
        "mode",
    )
    return dict(
        executions=[
            dict(
                **{key: row[key] for key in fields},
                source_event_freshness={
                    key: row["source_event_freshness"][key]
                    for key in (freshness if row["quantity"] else ("fresh", "mode"))
                },
            )
            for row in case["executions"]
        ],
        gaps=case.get("gaps", []),
        completed_labels=case["completed_labels"],
        open_positions=case.get("open_positions", 0),
        open_orders=case.get("open_orders", 0),
        unknown=case.get("unknown", []),
    )


def semantic_case(case):
    result = raw_semantic_case(case)
    result["completed_labels"] = [
        dict(row, book=dict(row["book"])) for row in result["completed_labels"]
    ]
    for row in result["completed_labels"]:
        prior = row["book"]["prior_closed_R"]
        assert isinstance(prior, (tuple, list))
        # dataclasses.asdict preserves this BookView tuple; JSON preserves its
        # ordered values as an array. No scalar conversion, rounding or tolerance.
        row["book"]["prior_closed_R"] = list(prior)
    return result


def first_difference(actual, expected, path=()):
    if actual == expected:
        return None
    if isinstance(actual, dict) and isinstance(expected, dict) and actual.keys() == expected.keys():
        for key in actual:
            result = first_difference(actual[key], expected[key], (*path, key))
            if result is not None:
                return result
    elif (
        type(actual) is type(expected)
        and isinstance(actual, (list, tuple))
        and len(actual) == len(expected)
    ):
        for i, (left, right) in enumerate(zip(actual, expected, strict=True)):
            result = first_difference(left, right, (*path, i))
            if result is not None:
                return result
    return dict(
        path=list(path),
        actual_type=type(actual).__name__,
        expected_type=type(expected).__name__,
        actual=actual,
        expected=expected,
        actual_repr=repr(actual),
        expected_repr=repr(expected),
    )


def persist_case_comparison(out, name, result, expected, volume):
    # Complete evidence must survive even the very first failed equality.
    write(out / (name + "-received.json"), result)
    comparison = dict(
        case=name,
        raw_first_difference=first_difference(
            raw_semantic_case(result), raw_semantic_case(expected)
        ),
        first_difference=first_difference(semantic_case(result), semantic_case(expected)),
        transport_normalization=(
            "Only completed_labels[*].book.prior_closed_R tuple -> list; "
            "values/order/scalars unchanged"
        ),
        no_numeric_tolerance=True,
        no_compared_field_removed=True,
    )
    comparison["equal"] = comparison["first_difference"] is None
    write(out / (name + "-comparison.json"), comparison)
    append(
        out / "synthetic-results.jsonl",
        dict(case=name, returned_complete_case=True, exact_comparison_equal=comparison["equal"]),
    )
    volume.commit()
    return comparison


def proof(common, out, grant, volume):
    import native_fixture
    import receive_root_scope
    from source_envelope import fill_witness

    expected = json.loads((common.OUT / "modal-migration/expected-native-runtime.json").read_text())
    cases = [
        ("held_gap_stop", {}),
        ("pending_partial_gap_stop", dict(partial=True)),
        ("unresolved_terminal_gap", dict(unresolved=True)),
        ("actual_entry_below_stop", dict(immediate=True)),
    ]
    received, comparisons = [], []
    for name, options in cases:
        grant.gate(new_start=True)
        append(
            out / "synthetic-constructions.jsonl",
            dict(
                case=name,
                at_utc=utc(),
                state="construction_about_to_be_called_actual_failure_may_be_unknown",
            ),
        )
        volume.commit()
        result = native_fixture.run_case(name, **options)
        comparisons.append(persist_case_comparison(out, name, result, expected[name], volume))
        received.append(name)
        volume.commit()
        gc.collect()
    grant.gate(new_start=True)
    receive_root_scope.run()
    events = {"TSLA": ((3,), ((3, 248.915, "open"),))}
    assert fill_witness(events, "TSLA", 7, 19, 248.91500000000002, 4, 3)["fresh"]
    assert not fill_witness(events, "TSLA", 7, 19, 248.9151, 4, 3)["fresh"]
    assert not fill_witness(events, "TSLA", 7, 19, 248.915000001, 4, 3)["fresh"]
    failures = [row for row in comparisons if not row["equal"]]
    write(
        out / "proof-comparison-summary.json",
        dict(
            cases=received,
            comparisons=comparisons,
            all_exact_comparisons_passed=not failures,
            first_divergence=failures[0] if failures else None,
            input_witnesses_completed=True,
            historical_roots_replayed=0,
        ),
    )
    volume.commit()
    assert not failures, "Exact runtime comparison failed: " + json.dumps(failures[0], default=str)
    return dict(
        status="complete_runtime_proof",
        synthetic_native_constructions=4,
        cases=received,
        exact_received_event_cash_maturity_and_gap_identity=True,
        original_four_packet_context_notice_reload_identity=True,
        decimal_roundtrip_guard_and_full_tick_rejection=True,
        historical_roots_replayed=0,
        new_labels=0,
        fits=0,
        accounts=0,
    )


def labels(common, out, grant, volume, manifest, shard, deadline):
    import native_labels
    from native_memory_v3 import release_completed_engine_memory
    from source_reader_root_scope import SourceReader

    geometry = json.loads((common.OUT / "geometry.json").read_text())
    roots = {row["confirmation_id"]: row for row in geometry["required"]}
    del geometry
    selected = manifest["partitions"][shard]
    assert not (set(selected) & set(manifest["prior_ids"]))
    assert len(set(selected)) == len(selected)
    folder = out / "labels"
    folder.mkdir(exist_ok=False)
    current = dict(identity=None)
    original_make = native_labels.make_engine

    def observed_constructor(*args, **kwargs):
        intent = dict(
            confirmation_id=current["identity"],
            at_utc=utc(),
            state="constructor_intent_actual_start_or_completion_may_be_unknown",
        )
        append(folder / "native-construction-intents.jsonl", intent)
        write(out / "active-root.json", intent)
        volume.commit()
        engine = None
        try:
            engine, strategy = original_make(*args, **kwargs)
            append(
                folder / "durable-constructed-engines.jsonl",
                dict(
                    confirmation_id=current["identity"],
                    actual_engine_constructed=True,
                    at_utc=utc(),
                    same_initialization_as_native_initializations_not_an_extra_start=True,
                ),
            )
            volume.commit()
        except BaseException:
            if engine is not None:
                try:
                    engine.dispose()
                except BaseException as disposal_error:
                    write(
                        out / "constructor-disposal-error.json",
                        dict(
                            at_utc=utc(),
                            confirmation_id=current["identity"],
                            error=repr(disposal_error),
                            durable_commit_not_guaranteed=True,
                        ),
                    )
            raise
        return engine, strategy

    native_labels.make_engine = observed_constructor
    reader, completed = None, []
    status = "complete_missing_root_shard"
    for identity in selected:
        if time.monotonic() >= deadline:
            status = "safe_root_boundary_finite_runtime_deadline"
            break
        try:
            grant.gate(new_start=True)
        except GrantStopped as error:
            status = "safe_root_boundary_relayed_authority"
            write(out / "authority-boundary.json", dict(at_utc=utc(), reason=str(error)))
            break
        current["identity"] = identity
        root = roots[identity]
        write(
            out / "active-root.json",
            dict(
                confirmation_id=identity,
                state="admitted_before_constructor",
                grant_version=grant.last["version"],
                actual_relay_at_utc=grant.last["relayed_at_utc"],
                at_utc=utc(),
            ),
        )
        volume.commit()
        if reader is None or reader.symbol != root["symbol"]:
            if reader is not None:
                reader.release_optional_caches()
            reader = SourceReader(root["symbol"])
        result = native_labels.one_attempt(root, reader, folder)
        append(folder / "results.jsonl", result)
        completed.append(identity)
        current["identity"] = None
        write(
            out / "active-root.json",
            dict(
                confirmation_id=None,
                state="disposed_root_durable_result",
                completed=len(completed),
                at_utc=utc(),
            ),
        )
        write(
            out / "checkpoint.json",
            dict(completed_ids=completed, selected_count=len(selected), shard=shard, at_utc=utc()),
        )
        volume.commit()
        release_completed_engine_memory(folder, identity)
        if len(completed) % 100 == 0:
            print(
                "MARTIN_LABEL_PROGRESS "
                + json.dumps(dict(shard=shard, completed=len(completed), selected=len(selected))),
                flush=True,
            )
    return dict(
        status=status,
        selected=len(selected),
        completed=len(completed),
        completed_ids=completed,
        current_root=current["identity"],
        actual_label_initializations=len(completed),
        fits=0,
        accounts=0,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--job-key", required=True)
    parser.add_argument("--phase", choices=["proof", "labels"], required=True)
    parser.add_argument("--shard", type=int, required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    assert str(args.out).startswith(TASK + "/modal-output/")
    for path in json.loads(os.environ["OC_MODAL_RUNTIME_PYTHONPATH"]):
        if path not in sys.path:
            sys.path.append(path)
    import modal

    manifest_path = REPO / args.manifest
    assert sha(manifest_path) == args.manifest_sha256
    manifest = json.loads(manifest_path.read_text())
    shape = manifest["phases"][args.phase]
    assert float(os.environ["OC_CPU"]) == shape["cpu"]
    assert float(os.environ["OC_MEMORY_GIB"]) == shape["memory_gib"]
    assert float(os.environ["OC_TIMEOUT_MIN"]) == shape["timeout_min"]
    assert len(json.loads(os.environ["OC_SHARD_COMMANDS"])) == shape["count"]
    assert os.environ["OC_RESOURCE_LIMITS"] == os.environ["OC_KEEP_REMOTE_OUTPUT"] == "1"
    assert not os.environ.get("OC_GPU")
    grant = LiveGrant(modal, manifest, args.manifest_sha256, args.job_key, args.phase)
    grant.gate(new_start=True)
    run_id = Path(os.environ["OC_LOG_PATH"]).stem
    assert 0 <= args.shard < shape["count"]
    invocation_claim = grant.claim(args.shard, run_id)
    raw = Path("/mnt/oc-out") / run_id / "raw" / f"shard-{args.shard}"
    raw.mkdir(parents=True, exist_ok=False)
    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    assert not out.exists()
    out.symlink_to(raw, target_is_directory=True)
    volume = modal.Volume.from_name("oc-out")
    cpu, wall = time.process_time(), time.monotonic()
    runtime = dict(
        at_utc=utc(),
        phase=args.phase,
        shard=args.shard,
        job_key=args.job_key,
        run_id=run_id,
        pid=os.getpid(),
        python=sys.version,
        modal_sdk=modal.__version__,
        modal_module_file=modal.__file__,
        worker_file=str(Path(__file__).resolve()),
        worker_sha256=sha(__file__),
        runtime_manifest_sha256=args.manifest_sha256,
        resources_declared=shape,
        function_call_id=os.environ.get("OC_MODAL_FUNCTION_CALL_ID"),
        app_id=os.environ.get("OC_MODAL_APP_ID"),
        function_id=os.environ.get("OC_MODAL_FUNCTION_ID"),
        input_id=os.environ.get("OC_MODAL_INPUT_ID"),
        task_id=os.environ.get("MODAL_TASK_ID"),
        raw_output_volume_path=str(raw),
        authority_source="live event-relayed scoped Dict; not local central-file freshness",
    )
    write(out / "runtime-start.json", runtime)
    write(out / "invocation-claim.json", invocation_claim)
    volume.commit()
    print("MARTIN_REMOTE_STARTED " + json.dumps(runtime), flush=True)
    result = dict(
        status="failed_retained", current_root="see durable active-root and constructor journal"
    )
    try:
        unpack(manifest)
        for row in manifest["dependency_files"]:
            assert sha(REPO / row["path"]) == row["sha256"], row["path"]
        proof_months = {"2024-01", "2024-02", "2024-06", "2024-12"}
        for row in manifest["data"]:
            path = REPO / row["path"]
            if args.phase == "proof" and not path.exists():
                assert any(f"2024-{month:02}" in str(path) for month in range(1, 13))
                assert not any(month in str(path) for month in proof_months)
                continue
            assert path.stat().st_size == row["bytes"] and sha(path) == row["sha256"]
        runtime["scientific_packages"] = {
            name: version(name) for name in manifest["expected_scientific_packages"]
        }
        assert runtime["scientific_packages"] == manifest["expected_scientific_packages"]
        write(out / "runtime-versions.json", runtime)
        sys.path.insert(0, str(REPO / TASK))
        import common

        common.gate = grant.gate
        original_save = common.save

        def save_received(path, value):
            path = Path(path)
            if path.parent == common.OUT and (
                path.name.startswith("native-fixture-")
                or path.name == "root-scope-input-reception.json"
            ):
                path = out / path.name
            original_save(path, value)

        common.save = save_received
        if args.phase == "proof":
            result = proof(common, out, grant, volume)
        else:
            result = labels(
                common,
                out,
                grant,
                volume,
                manifest,
                args.shard,
                wall + shape["timeout_min"] * 60 - 300,
            )
    except BaseException as error:
        result["error"] = dict(type=type(error).__name__, text=str(error))
        raise
    finally:
        synthetic = {}
        for name in ("synthetic-constructions", "synthetic-results"):
            path = out / (name + ".jsonl")
            synthetic[name] = (
                [json.loads(line)["case"] for line in path.read_text().splitlines()]
                if path.exists()
                else []
            )
        result["actual_synthetic_case_journals"] = synthetic
        result["synthetic_construction_intent_without_returned_case_UNKNOWN"] = sorted(
            set(synthetic["synthetic-constructions"]) - set(synthetic["synthetic-results"])
        )
        ledgers = {}
        for name in (
            "native-construction-intents",
            "native-initializations",
            "durable-constructed-engines",
            "results",
        ):
            path = out / "labels" / (name + ".jsonl")
            ledgers[name] = (
                [json.loads(line)["confirmation_id"] for line in path.read_text().splitlines()]
                if path.exists()
                else []
            )
        result["actual_native_ledger_counts"] = {name: len(ids) for name, ids in ledgers.items()}
        counters = {name: Counter(ids) for name, ids in ledgers.items()}
        result["native_ledger_id_counters"] = {
            name: dict(counts) for name, counts in counters.items()
        }
        result["duplicate_ledger_ids"] = {
            name: {identity: count for identity, count in counts.items() if count != 1}
            for name, counts in counters.items()
        }
        active_path = out / "active-root.json"
        result["actual_active_root"] = (
            json.loads(active_path.read_text()) if active_path.exists() else None
        )
        result["construction_intents_without_confirmed_initialization_UNKNOWN"] = sorted(
            set(ledgers["native-construction-intents"])
            - set(ledgers["durable-constructed-engines"])
        )
        result["constructed_without_result"] = sorted(
            set(ledgers["durable-constructed-engines"]) - set(ledgers["results"])
        )
        result["initialization_or_result_reconciliation_required"] = bool(
            result["construction_intents_without_confirmed_initialization_UNKNOWN"]
            or result["constructed_without_result"]
            or any(result["duplicate_ledger_ids"].values())
            or counters["durable-constructed-engines"] != counters["native-initializations"]
            or counters["native-initializations"] != counters["results"]
            or (result["actual_active_root"] or {}).get("confirmation_id") is not None
        )
        result.update(
            at_utc=utc(),
            CPU_s=time.process_time() - cpu,
            wall_s=time.monotonic() - wall,
            maxrss_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            runtime_manifest_sha256=args.manifest_sha256,
        )
        write(out / "process.json", result)
        files = [p for p in out.rglob("*") if p.is_file() and p.name != "returned-files.json"]
        write(
            out / "returned-files.json",
            dict(
                files=[
                    dict(
                        path=str(p.relative_to(out)),
                        bytes=p.stat().st_size,
                        sha256=sha(p),
                    )
                    for p in sorted(files)
                ]
            ),
        )
        volume.commit()
        print(
            "MARTIN_REMOTE_TERMINAL "
            + json.dumps({key: value for key, value in result.items() if key != "completed_ids"}),
            flush=True,
        )


if __name__ == "__main__":
    main()
