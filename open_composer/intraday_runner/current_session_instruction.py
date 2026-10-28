"""Prospective Oct20 instruction reception; never retag an expired forecast."""

from __future__ import annotations

import copy
import importlib
import json
import sys
from pathlib import Path

from open_composer.intraday_runner.current_initialization_controls import aware, number
from open_composer.intraday_runner.source_method_bindings import bound_bytes

SESSION = "SIX-CURRENT-SESSION-20261020"
MAIN = "bef005c833c469800f50f12527f6681f9a3e8e791e4af2888d062a6944af02c5"
OWNER = "880ffa56f0338452466eacb7b37f1c9c75d78c8496112b4699ebffc706a9f464"
ENVELOPE = "dceb83e917180f41cbfe88692b4096c9956f6ecd603b54d6a6a9af768097a4c5"
CONTRACT = "077f2a4651728eac68ba43e8d3da959307a157ab6560343babd4434fa79722de"
FOLDER = (
    "reports/research/program/owner-profit-delivery-plan-20261017/"
    "current-paper-science-20261020/later-session-20261020"
)
START = "2026-10-20T14:40:00Z"
END = "2026-10-20T19:30:00Z"
PUBLISH = "2026-10-20T18:45:00Z"
CANCEL = "2026-10-20T19:55:00Z"


def policies():
    from open_composer.intraday_runner.current_initialization_episode import POLICIES
    from open_composer.intraday_runner.validation_account_partition import EQUAL, HIERARCHICAL

    return {**POLICIES, EQUAL: "MULTI_EQUAL", HIERARCHICAL: "MULTI_HIERARCHICAL"}


def receive_scope(root, authority):
    selection = authority["current_day_selection"]
    value = json.loads(bound_bytes(root, selection))
    envelope = authority["prospective_session"]
    calendar = json.loads(bound_bytes(root, envelope))
    if (
        selection.get("sha256") != MAIN
        or value["owner_directive"].get("sha256") != OWNER
        or envelope.get("sha256") != ENVELOPE
        or authority.get("session_id") != SESSION
        or authority.get("application_day") != "2026-10-20"
        or authority.get("reference_day") != "2026-10-19"
        or authority.get("task_id") not in policies()
        or calendar["latest_new_risk_dispatch_utc"] != END
        or calendar["pending_initial_order_cancel_by_utc"] != CANCEL
    ):
        raise ValueError("unreceived prospective session")
    bound_bytes(root, value["owner_directive"])
    if authority.get("maintenance_plan") is not None:
        raise ValueError("new instruction cannot replay funding maintenance")
    return value


def normalize(value, policy):
    sizes = {"BASE": 27, "H5": 31, "LSTM": 10, "BASE_STATE_BUDGET": 27}
    if policy not in sizes:
        raise ValueError("composite instructions require independently accepted child books")
    symbols, weights = value["symbols"], [number(x) for x in value["weights"]]
    tolerance = number("1e-12") if policy == "LSTM" else number(0)
    if (
        value.get("task_id") != "CURRENT-PAPER-SCIENCE-20261020"
        or value.get("session_id") != SESSION
        or value.get("policy") != policy
        or value.get("application_day") != "2026-10-20"
        or value.get("reference_day") != "2026-10-19"
        or value.get("capital_USD") != 20000
        or value.get("operating_authority") is not False
        or value.get("targets_are_holdings_or_orders") is not False
        or len(symbols) != sizes[policy]
        or len(set(symbols)) != len(symbols)
        or len(weights) != len(symbols)
        or any(w > number(".2") + tolerance for w in weights)
        or sum(weights) > 1 + tolerance
        or value.get("consume_before") != END
        or value.get("dispatch_window") != [START, END]
        or value.get("cancel_pending_by") != CANCEL
        or value.get("holding_authority_cap") != "2026-11-14T00:00:00Z"
        or value["contract"].get("sha256") != CONTRACT
    ):
        raise ValueError("prospective instruction mapping differs")
    if any(number(value["raw_reference_marks"][s]) <= 0 for s in symbols):
        raise ValueError("missing original raw reference")
    if not (
        aware("2026-10-20T00:00:00Z")
        <= aware(value["computation_started_at"])
        <= aware(value["computation_completed_at"])
        <= aware(value["instruction_published_at"])
        < aware(PUBLISH)
    ):
        raise ValueError("instruction clocks differ")
    if policy == "LSTM":
        if value.get("new_prediction") is not True:
            raise ValueError("LSTM requires actual new current inference")
    else:
        origin = value["origin_scientific"]
        if (
            value.get("new_prediction") is not False
            or value.get("original_instruction_expired") is not True
            or type(value.get("K")) is not int
            or not 0 <= value["K"] <= 5
            or sum(w > 0 for w in weights) > 5
            or not (
                aware(origin["completed_at"])
                <= aware(value["adopted_at"])
                <= aware(value["instruction_published_at"])
            )
            or any(
                value[key] != origin[key]
                for key in (
                    "symbols",
                    "weights",
                    "raw_reference_marks",
                    "source",
                    "source_complete",
                    "input",
                    "input_complete",
                    "model_bindings",
                    "computation_started_at",
                    "computation_completed_at",
                    "published_at",
                    "completed_at",
                )
            )
        ):
            raise ValueError("adoption changed original scientific evidence")
    return dict(
        forecast=dict(
            symbols=list(symbols),
            weights=list(value["weights"]),
            reference_marks=dict(value["raw_reference_marks"]),
            decision_reason=value.get("cash_cause", "received_current_learned_ensemble"),
        ),
        received_scientific_component=value,
        normalized_field_mapping_only=True,
        runtime_K_rank_weight_recalculation=False,
    )


def receive(root, authority, *, clock, child_instruction=False):
    from open_composer.intraday_runner.current_initialization_episode import REVIEWER

    root = Path(root)
    receive_scope(root, authority)
    policy = policies()[authority["task_id"]]
    if type(child_instruction) is not bool or child_instruction != policy.startswith("MULTI_"):
        raise ValueError("flat parent or wrong scientific receiver mode")
    if policy in {"H5", "BASE_STATE_BUDGET"} and sys.version_info[:2] != (3, 11):
        raise ValueError("producer CPython3.11 required")
    folder = root / FOLDER
    spec = authority["scientific_consumer"]
    paths = {
        "consumer": folder / "session_consumer.py",
        "manifest": folder / "implementation-manifest-M1.json",
        "schema": folder / "consumer-schema.json",
        "contract": folder / "current-session-contract.json",
        "package": folder / policy / "current-package.json",
        "final": folder / policy / "final-manifest.json",
    }
    saved = {}
    for key, path in paths.items():
        if Path(spec[key]["path"]) != path or path != path.resolve():
            raise ValueError("noncanonical prospective component")
        saved[key] = bound_bytes(root, spec[key])
    acceptance = authority["scientific_acceptance"]
    if Path(acceptance["path"]) != folder / f"independent-{policy}-result-review.json":
        raise ValueError("wrong prospective result review")
    review = json.loads(bound_bytes(root, acceptance))
    if (
        review.get("reviewer") != REVIEWER
        or review.get("independent") is not True
        or review.get("verdict") != "approve_result"
        or review.get("component_result_accepted") is not True
        or review.get("session_id") != SESSION
        or review.get("policy") != policy
        or review.get("target") != spec["final"]
    ):
        raise ValueError("prospective result not independently accepted")
    package = json.loads(saved["package"])
    for key in ("package", "consumer", "schema", "contract"):
        if review.get(key) != spec[key]:
            raise ValueError("scientific review binding differs")
    if (
        review.get("implementation") != spec["manifest"]
        or review.get("forecast") != package["output"]
    ):
        raise ValueError("scientific implementation/output differs")
    rows = json.loads(saved["manifest"])["files"]
    if spec["consumer"] not in rows:
        raise ValueError("consumer outside implementation")
    for row in rows:
        bound_bytes(root, row)
    for path in folder.glob("*.py"):
        cached = sys.modules.get(path.stem)
        if cached is not None and Path(getattr(cached, "__file__", "")).resolve() != path:
            raise ValueError("foreign cached scientific module")
    sys.path.insert(0, str(folder))
    try:
        module = importlib.import_module("session_consumer")
        result = module.receive_current_package(spec["package"]["path"], for_execution=True)
    finally:
        sys.path.remove(str(folder))
    for key in ("package", "final", "consumer", "schema", "contract"):
        if result[key] != spec[key]:
            raise ValueError("returned instruction binding differs")
    if (
        result["review"] != acceptance
        or result["forecast"] != package["output"]
        or result["implementation"] != spec["manifest"]
        or not aware(clock()) < aware(END)
    ):
        raise ValueError("returned instruction review or expiry differs")
    for key in paths:
        if bound_bytes(root, spec[key]) != saved[key]:
            raise ValueError("component changed during reception")
    bound_bytes(root, acceptance)
    for row in rows:
        bound_bytes(root, row)
    return result if child_instruction else normalize(result, policy)


def runtime_class(root, authority):
    """An absent/unaccepted child adapter blocks only its composite.

    Add-only independent child implementation can be installed later without
    changing any file in an already-active standalone's exact closure.
    """
    from open_composer.intraday_runner.current_initialization_runtime import (
        CurrentInitializationRuntime,
    )
    from open_composer.intraday_runner.validation_account_partition import EQUAL, HIERARCHICAL

    if authority["task_id"] not in {EQUAL, HIERARCHICAL}:
        return CurrentInitializationRuntime
    adapter = authority.get("segregated_child_adapter")
    review = json.loads(bound_bytes(root, authority["operating_acceptance"]))
    path = Path(root) / "open_composer/intraday_runner/current_composite_child_runtime.py"
    if (
        not isinstance(adapter, dict)
        or Path(adapter["path"]) != path
        or adapter not in authority["code_bindings"]
        or review.get("accepted_segregated_child_runtime") is not True
        or review.get("segregated_child_adapter") != adapter
    ):
        raise ValueError("actual segregated child runtime not received")
    raw = bound_bytes(root, adapter)
    name = "open_composer.intraday_runner.current_composite_child_runtime"
    cached = sys.modules.get(name)
    if cached is not None and Path(getattr(cached, "__file__", "")).resolve() != path:
        raise ValueError("foreign child adapter")
    module = importlib.import_module(name)
    if (
        not issubclass(module.CurrentCompositeRuntime, CurrentInitializationRuntime)
        or bound_bytes(root, adapter) != raw
    ):
        raise ValueError("child implementation drift")
    return module.CurrentCompositeRuntime


def continue_empty_base(runtime, plan_binding):
    """One explicit gen1 instruction/code successor; no funding or book reset."""
    from open_composer.intraday_runner.source_activity_reception import bind
    from open_composer.intraday_runner.source_dispatch_journal import _hash
    from open_composer.intraday_runner.validation_account_partition import BASE

    if (
        runtime.task != BASE
        or not runtime._operation_held
        or not runtime.partition.held
        or runtime.current_phase != "decision"
        or runtime.auth.get("session_id") != SESSION
    ):
        raise ValueError("episode continuation requires exact locked BASE native decision")
    plan = json.loads(bound_bytes(runtime.root, plan_binding))
    proof = json.loads(bound_bytes(runtime.root, plan["precondition"]))
    review = json.loads(bound_bytes(runtime.root, runtime.auth["operating_acceptance"]))
    if (
        plan.get("new_authority") != runtime.authority
        or review.get("accepted_current_day_continuation") is not True
        or review.get("episode_continuation_precondition") != plan["precondition"]
        or review.get("episode_continuation_code") != bind(Path(__file__).resolve())
        or plan.get("capital_flow_USD") != 0
    ):
        raise ValueError("exact zero-flow continuation not reviewed")
    integration = json.loads(bound_bytes(runtime.root, plan["integration_receipt"]))
    closure = json.loads(bound_bytes(runtime.root, integration["installed_closure"]))
    if (
        integration.get("status") != "integrated_verified_inert"
        or integration.get("task_id") != BASE
        or integration.get("accepted_review") != runtime.auth["operating_acceptance"]
        or closure.get("installed_code_bindings") != runtime.auth["code_bindings"]
    ):
        raise ValueError("actual Main successor integration not received")
    old = json.loads(bound_bytes(runtime.root, proof["old_authority"]))
    allowed = {
        "code_bindings",
        "operating_acceptance",
        "scientific_acceptance",
        "scientific_consumer",
        "spec",
        "policy",
        "paper_validation",
        "current_day_selection",
        "authorized_at",
        "scope_note",
    }
    added = {"session_id", "prospective_session"}
    if (
        set(runtime.auth) != set(old) | added
        or any(old[k] != runtime.auth[k] for k in old if k not in allowed)
        or old.get("capital_usd") != 20000
        or old.get("task_id") != BASE
        or proof.get("canonical_head_sha256")
        != "5b3569ed75a618f43ed549c46765a51be7efba54b132209baef77db2e17c827c"
        or proof["old_authority"].get("sha256")
        != "696e2b8e210830ed2cfc8d86b124e8eca629d641b778db717842d20258a77dc9"
        or proof["registry_pointer"].get("sha256")
        != "77f9dcbf6774d293ca8d1fc82bca9e04f199657deeb84a207be48636959aea7c"
    ):
        raise ValueError("not the actual funded gen1 predecessor")
    for binding in proof["retained_bindings"]:
        bound_bytes(runtime.root, binding)
    for key in ("head", "revision", "consumed_marker", "actual_outcome", "outcome_review"):
        bound_bytes(runtime.root, proof[key])
    pointer_path = Path(proof["registry_pointer"]["path"])
    expected_pointer = runtime.partition.directory / (BASE + ".json")
    if pointer_path != expected_pointer or pointer_path != pointer_path.resolve():
        raise ValueError("wrong current registry path")
    pointer_raw = bound_bytes(runtime.root, proof["registry_pointer"])
    pointer = json.loads(pointer_raw)
    if pointer["authority"] != proof["old_authority"]:
        raise ValueError("predecessor registry authority differs")
    current = runtime.store.load()
    if current["generation"] != 1 or _hash(current) != proof["canonical_head_sha256"]:
        raise ValueError("actual funded checkpoint changed; no replay")
    before = current["snapshot"]
    if (
        any(before[k] for k in ("pending", "consumed_ids", "applied_fill_ids", "fills", "fees"))
        or before["cashbook"]
        != dict(cash=20000, sales=[], purchases=[], dividends=[], lots={}, next_id=0)
        or (runtime.directory / "initial-decision.json").exists()
        or list(runtime.journal.directory.glob("*.json"))
        or before["evidence"]["risk"]["halted"] is not False
        or before["evidence"]["risk"]["killed"] is not False
    ):
        raise ValueError("predecessor is no longer the empty unfired funded sleeve")
    package = runtime.current_scientific_package
    component = package["received_scientific_component"]
    normalize(component, "BASE")
    if component["review"] != runtime.auth["scientific_acceptance"]:
        raise ValueError("wrong accepted successor instruction")
    audit = Path(plan["output"])
    if audit.exists() or runtime.directory not in audit.parents:
        raise ValueError("continuation already attempted or outside owned ledger")
    runtime.ensure_directory(audit)
    runtime.save_capture(
        audit / "started.json",
        dict(plan=plan_binding, predecessor=_hash(current), capital_flow_USD=0),
    )
    proposed = copy.deepcopy(before)
    proposed["evidence"].setdefault("instruction_adoptions", []).append(
        dict(
            predecessor=_hash(current),
            prior_authority=proof["old_authority"],
            authority=runtime.authority,
            package=component["package"],
            review=component["review"],
            origin_scientific=component["origin_scientific"],
            adopted_at=runtime.clock().isoformat(),
            capital_flow_USD=0,
            prior_scientific_package_sha256=before["evidence"]["scientific_package_sha256"],
        )
    )
    proposed["evidence"]["scientific_package_sha256"] = _hash(package)
    # Allocation flows, actual cash/positions/IDs and every risk field stay exact.
    try:
        runtime.require_phase("decision")
        runtime.store.commit(proposed, expected_head_sha256=_hash(current))
        if pointer_path.read_bytes() != pointer_raw:
            raise ValueError("registry changed before prospective CAS")
        pointer["authority"] = runtime.authority
        runtime.write_text(pointer_path, json.dumps(pointer, sort_keys=True, indent=2) + "\n")
        runtime.require_phase("decision")
        runtime.save_capture(
            audit / "completed.json",
            dict(
                plan=plan_binding,
                checkpoint=_hash(runtime.store.load()),
                registry=bind(pointer_path),
                capital_flow_USD=0,
            ),
        )
    except Exception:
        runtime.save_capture(
            audit / "held.json",
            dict(plan=plan_binding, replay_forbidden=True, capital_flow_USD=0),
        )
        raise


def continue_existing_base_code(runtime, plan_binding):
    """Exact GEN6 code-only registry successor for one GET-only settle invocation.

    No checkpoint, scientific instruction, capital, lot, reservation, consumed ID,
    latch, or HWM is edited. The appended audit and registry CAS cannot be reused
    as initialization, funding, new-risk or resend authority.
    """
    from open_composer.intraday_runner.source_activity_reception import bind
    from open_composer.intraday_runner.source_dispatch_journal import _hash
    from open_composer.intraday_runner.validation_account_partition import BASE

    if (
        runtime.task != BASE
        or not runtime._operation_held
        or not runtime.partition.held
        or runtime.current_phase != "settle"
        or runtime.auth.get("session_id") != SESSION
    ):
        raise ValueError("code successor requires locked BASE GET-only settlement")
    plan = json.loads(bound_bytes(runtime.root, plan_binding))
    proof = json.loads(bound_bytes(runtime.root, plan["precondition"]))
    review = json.loads(bound_bytes(runtime.root, runtime.auth["operating_acceptance"]))
    if (
        plan.get("new_authority") != runtime.authority
        or plan.get("capital_flow_USD") != 0
        or plan.get("checkpoint_mutation") is not False
        or review.get("accepted_code_maintenance") is not True
        or review.get("code_continuation_precondition") != plan["precondition"]
        or review.get("code_continuation_code") != bind(Path(__file__).resolve())
    ):
        raise ValueError("exact code-only GEN6 continuation not reviewed")
    integration = json.loads(bound_bytes(runtime.root, plan["integration_receipt"]))
    closure = json.loads(bound_bytes(runtime.root, integration["installed_closure"]))
    if (
        integration.get("status") != "integrated_verified_inert"
        or integration.get("task_id") != BASE
        or integration.get("accepted_review") != runtime.auth["operating_acceptance"]
        or closure.get("installed_code_bindings") != runtime.auth["code_bindings"]
    ):
        raise ValueError("actual code successor integration absent")
    old = json.loads(bound_bytes(runtime.root, proof["old_authority"]))
    if (
        set(old) != set(runtime.auth)
        or old["task_id"] != BASE
        or old["capital_usd"] != 20000
        or any(
            old[k] != runtime.auth[k]
            for k in old
            if k not in {"code_bindings", "operating_acceptance"}
        )
        or proof["actual_outcome"]["sha256"]
        != "cf20a15e5ad523550a39efaeb76f6555bf0c17a6603fc6e95e823496de7e2be1"
        or proof["outcome_review"]["sha256"]
        != "4daf95aae62c0648e123472afad419ea3e89c74078003362c54053a650cf40f4"
    ):
        raise ValueError("not the actual unchanged GEN6 operating authority")
    outcome = json.loads(bound_bytes(runtime.root, proof["actual_outcome"]))
    if (
        proof["old_authority"] != outcome["authority"]
        or proof["registry_pointer"] != outcome["pointer"]
        or proof["head"] != outcome["head"]
        or proof["revision"] != outcome["current_revision"]
        or proof["canonical_head_sha256"] != outcome["head_value"]["sha256"]
        or outcome["head_value"]["generation"] != 6
    ):
        raise ValueError("precondition differs from received actual GEN6 outcome")
    for key in (
        "head",
        "revision",
        "initial_decision",
        "consumed_marker",
        "actual_outcome",
        "outcome_review",
    ):
        bound_bytes(runtime.root, proof[key])
    for row in proof["retained_bindings"]:
        bound_bytes(runtime.root, row)
    pointer_path = runtime.partition.directory / (BASE + ".json")
    if (
        Path(proof["registry_pointer"]["path"]) != pointer_path
        or pointer_path != pointer_path.resolve()
    ):
        raise ValueError("registry predecessor path differs")
    pointer_raw = bound_bytes(runtime.root, proof["registry_pointer"])
    pointer = json.loads(pointer_raw)
    if pointer.get("authority") != proof["old_authority"]:
        raise ValueError("registry authority is not the exact predecessor")
    current = runtime.store.load()
    if (
        current["generation"] != 6
        or _hash(current) != proof["canonical_head_sha256"]
        or bind(runtime.store.directory / "revision-00000006.json") != proof["revision"]
        or bind(runtime.store.directory / "head.json") != proof["head"]
        or bind(runtime.directory / "initial-decision.json") != proof["initial_decision"]
    ):
        raise ValueError("GEN6 financial/history state changed; no automatic reapply")
    audit = Path(plan["output"])
    if audit.exists() or runtime.directory not in audit.parents or audit != audit.resolve():
        raise ValueError("code continuation already attempted or aliased")
    runtime.ensure_directory(audit)
    runtime.save_capture(
        audit / "started.json",
        dict(
            plan=plan_binding,
            predecessor=_hash(current),
            capital_flow_USD=0,
            checkpoint_mutation=False,
        ),
    )
    try:
        runtime.read_guard()
        runtime.require_phase("settle")
        if runtime.store.load() != current or pointer_path.read_bytes() != pointer_raw:
            raise ValueError("code continuation predecessor changed before CAS")
        pointer["authority"] = runtime.authority
        runtime.write_text(pointer_path, json.dumps(pointer, sort_keys=True, indent=2) + "\n")
        runtime.read_guard()
        runtime.require_phase("settle")
        if runtime.store.load() != current:
            raise ValueError("unexpected financial change during code-only continuation")
        runtime.save_capture(
            audit / "completed.json",
            dict(
                plan=plan_binding,
                checkpoint=_hash(current),
                registry=bind(pointer_path),
                capital_flow_USD=0,
                checkpoint_mutation=False,
                permits_only_actual_settlement=True,
            ),
        )
        runtime.require_phase("settle")
    except Exception:
        runtime.save_capture(
            audit / "held.json",
            dict(
                plan=plan_binding,
                replay_forbidden=True,
                capital_flow_USD=0,
                checkpoint_mutation=False,
            ),
        )
        raise
