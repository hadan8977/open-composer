"""Exact Oct20 continuation and read-only mapping of accepted current science.

Stable sleeve identities retain their Oct19 history. This episode never changes
a scientific clock, computes a weight, refreshes a source, or grants funding.
"""

from __future__ import annotations

import copy
import importlib
import json
import sys
from pathlib import Path

from open_composer.intraday_runner.current_initialization_controls import aware, number
from open_composer.intraday_runner.source_dispatch_journal import _hash
from open_composer.intraday_runner.source_method_bindings import bound_bytes
from open_composer.intraday_runner.validation_account_partition import BASE, H5, LSTM, STATE

DAY = "2026-10-20"
REFERENCE = "2026-10-19"
MAIN_SHA = "2fd36f7997a7f775f11a5f879e1e25865e08bc7261d718e0bbd1a1354c003a2e"
OWNER_SHA = "9334abd1126f460820dd10cffc12df9580590d251a19c90b824e970e17bc417a"
SCIENCE_TASK = "CURRENT-PAPER-SCIENCE-20261020"
POLICIES = {BASE: "BASE", H5: "H5", LSTM: "LSTM", STATE: "BASE_STATE_BUDGET"}
FOLDER = (
    "reports/research/program/owner-profit-delivery-plan-20261017/current-paper-science-20261020"
)
REVIEWER = "93af0483-230a-4632-8b48-c63cd53a01f7"


def receive_day(root, authority):
    """Current-day owner selection is an additional, exact authority boundary."""
    if "session_id" in authority:
        from open_composer.intraday_runner.current_session_instruction import receive_scope

        return receive_scope(root, authority)
    selection = authority["current_day_selection"]
    value = json.loads(bound_bytes(root, selection))
    if (
        selection.get("sha256") != MAIN_SHA
        or value["owner_directive"].get("sha256") != OWNER_SHA
        or authority.get("application_day") != DAY
        or authority.get("reference_day") != REFERENCE
        or authority.get("task_id") not in POLICIES
    ):
        raise ValueError("unreceived current episode")
    bound_bytes(root, value["owner_directive"])
    return value


def normalize_received(value, policy):
    if "session_id" in value:
        from open_composer.intraday_runner.current_session_instruction import normalize

        return normalize(value, policy)
    symbols, weights = value["symbols"], [number(x) for x in value["weights"]]
    size = {"BASE": 27, "H5": 31, "LSTM": 10, "BASE_STATE_BUDGET": 27}[policy]
    tolerance = number("1e-12") if policy == "LSTM" else number(0)
    if (
        value.get("task_id") != SCIENCE_TASK
        or value.get("policy") != policy
        or value.get("episode_day") != DAY
        or value.get("application_day") != DAY
        or value.get("reference_day") != REFERENCE
        or value.get("capital_USD") != 20000
        or value.get("operating_authority") is not False
        or value.get("targets_are_holdings_or_orders") is not False
        or len(symbols) != size
        or len(set(symbols)) != size
        or len(weights) != size
        or any(w > number(".2") + tolerance for w in weights)
        or sum(weights) > 1 + tolerance
        or value.get("consume_before") != DAY + "T13:41:00Z"
        or value.get("dispatch_window") != [DAY + "T13:40:00Z", DAY + "T13:41:00Z"]
        or value.get("holding_authority_cap") != "2026-11-14T00:00:00Z"
    ):
        raise ValueError("current policy mapping differs")
    if any(number(value["raw_reference_marks"][s]) <= 0 for s in symbols):
        raise ValueError("missing current raw reference")
    if not (
        aware(DAY + "T00:00:00Z")
        <= aware(value["computation_started_at"])
        <= aware(value["computation_completed_at"])
        <= aware(value["published_at"])
        <= aware(value["completed_at"])
        < aware(DAY + "T13:30:00Z")
    ):
        raise ValueError("current scientific clocks differ")
    if policy != "LSTM" and (
        type(value.get("K")) is not int
        or not 0 <= value["K"] <= 5
        or sum(w > 0 for w in weights) > 5
    ):
        raise ValueError("current participation differs")
    return dict(
        forecast=dict(
            symbols=list(symbols),
            weights=list(value["weights"]),
            reference_marks=dict(value["raw_reference_marks"]),
            decision_reason=value["cash_cause"],
        ),
        received_scientific_component=value,
        normalized_field_mapping_only=True,
        runtime_K_rank_weight_recalculation=False,
    )


def receive(root, authority, *, clock):
    if "session_id" in authority:
        from open_composer.intraday_runner.current_session_instruction import receive as later

        return later(root, authority, clock=clock)
    root = Path(root)
    receive_day(root, authority)
    policy = POLICIES[authority["task_id"]]
    folder = root / FOLDER
    spec = authority["scientific_consumer"]
    paths = {
        "consumer": folder / "current_paper_consumer.py",
        "manifest": folder / "implementation-manifest.json",
        "schema": folder / "consumer-schema.json",
        "contract": folder / "prospective-contract.json",
        "package": folder / policy / "current-package.json",
        "final": folder / policy / "final-manifest.json",
    }
    saved = {}
    for key, path in paths.items():
        if Path(spec[key]["path"]) != path or path != path.resolve():
            raise ValueError("noncanonical current science")
        saved[key] = bound_bytes(root, spec[key])
    acceptance = authority["scientific_acceptance"]
    if Path(acceptance["path"]) != folder / f"independent-{policy}-result-review.json":
        raise ValueError("wrong current scientific review")
    review = json.loads(bound_bytes(root, acceptance))
    if (
        review.get("task_id") != SCIENCE_TASK
        or review.get("policy") != policy
        or review.get("reviewer") != REVIEWER
        or review.get("verdict") != "approve_result"
        or review.get("component_result_accepted") is not True
        or review.get("target") != spec["final"]
    ):
        raise ValueError("current scientific result not accepted")
    rows = json.loads(saved["manifest"])["files"]
    if spec["consumer"] not in rows:
        raise ValueError("consumer outside accepted implementation")
    for row in rows:
        bound_bytes(root, row)
    # All scientific imports are uniquely task-local; reject cached foreign code.
    local_modules = {p.stem: p for p in folder.glob("*.py")}
    for name, path in local_modules.items():
        cached = sys.modules.get(name)
        if cached is not None and Path(getattr(cached, "__file__", "")).resolve() != path:
            raise ValueError("foreign cached scientific module")
    sys.path.insert(0, str(folder))
    try:
        module = importlib.import_module("current_paper_consumer")
        result = module.receive_current_package(spec["package"]["path"], for_execution=True)
    finally:
        sys.path.remove(str(folder))
    package = json.loads(saved["package"])
    if (
        result["review"] != acceptance
        or result["package"] != spec["package"]
        or result["final"] != spec["final"]
        or result["consumer"] != spec["consumer"]
        or result["schema"] != spec["schema"]
        or result["forecast"] != package["forecast"]
        or not aware(clock()) < aware(result["consume_before"])
    ):
        raise ValueError("current consumer receipt or clock differs")
    for key in paths:
        if bound_bytes(root, spec[key]) != saved[key]:
            raise ValueError("scientific publication changed during reception")
    bound_bytes(root, acceptance)
    for row in rows:
        bound_bytes(root, row)
    return normalize_received(result, policy)


def adopt_empty_funding_episode(proposed, predecessor, package, authority):
    """Append new instruction provenance within the one authorized flow revision."""
    value = copy.deepcopy(proposed)
    old = predecessor["snapshot"]
    evidence = value["evidence"]
    if (
        predecessor["generation"] != 0
        or any(old[k] for k in ("pending", "consumed_ids", "applied_fill_ids", "fills", "fees"))
        or old["cashbook"]
        != dict(cash=10000, sales=[], purchases=[], dividends=[], lots={}, next_id=0)
        or old["evidence"].get("episode_continuations")
        or len(evidence.get("allocation_flows", [])) != 1
        or value["cashbook"]["cash"] != 20000
        or authority.get("application_day") != DAY
        or authority["task_id"] != BASE
    ):
        raise ValueError("not the exact unfunded empty episode predecessor")
    component = package["received_scientific_component"]
    normalize_received(component, "BASE")
    if component["review"] != authority["scientific_acceptance"]:
        raise ValueError("unaccepted episode package")
    evidence["episode_continuations"] = [
        dict(
            prior_scientific_package_sha256=old["evidence"]["scientific_package_sha256"],
            prior_actions_observation_day=old["evidence"]["actions_observation_day"],
            predecessor_sha256=_hash(predecessor),
            current_day_selection=authority["current_day_selection"],
            application_day=DAY,
            reference_day=REFERENCE,
            package=component["package"],
            review=component["review"],
            source=component["source"],
            source_complete=component["source_complete"],
            scientific_package_sha256=_hash(package),
            historical_results_rewritten=False,
        )
    ]
    evidence["scientific_package_sha256"] = _hash(package)
    evidence["actions_observation_day"] = DAY
    evidence["actions_current"] = True
    return value
