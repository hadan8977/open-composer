"""Read-only STATE allocation reception; no rank/K/weight recomputation."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

from open_composer.intraday_runner.current_initialization_controls import aware, number
from open_composer.intraday_runner.source_method_bindings import bound_bytes
from open_composer.intraday_runner.validation_account_partition import STATE

FOLDER = (
    "reports/research/program/owner-profit-delivery-plan-20261017/"
    "current-synthesis-receivers-20261019"
)
REVIEWER = "93af0483-230a-4632-8b48-c63cd53a01f7"


def normalize_received(result):
    symbols = result["symbols"]
    weights = [number(x) for x in result["weights"]]
    if (
        result.get("task_id") != STATE
        or result.get("policy") != "BASE_STATE_BUDGET"
        or result.get("capital_USD") != 20000
        or result.get("reference_day") != "2026-10-16"
        or result.get("paper_ready") is not False
        or result.get("targets_are_holdings_or_orders") is not False
        or len(symbols) != 27
        or len(set(symbols)) != 27
        or "WBA" in symbols
        or len(weights) != 27
        or any(x > number(".2") for x in weights)
        or sum(weights) > 1
        or sum(x > 0 for x in weights) > 5
        or type(result.get("K")) is not int
        or not 0 <= result["K"] <= 5
        or result.get("historical_strict_prior_BASE_reference_parity") is not False
        or result.get("consume_before") != "2026-10-19T13:41:00Z"
        or result.get("dispatch_window") != ["2026-10-19T13:40:00Z", "2026-10-19T13:41:00Z"]
        or result.get("holding_authority_cap") != "2026-11-14T00:00:00Z"
    ):
        raise ValueError("unreceived current STATE policy")
    if any(number(result["raw_reference_marks"][s]) <= 0 for s in symbols):
        raise ValueError("unpriced current STATE units")
    return dict(
        forecast=dict(
            symbols=list(symbols),
            weights=list(result["weights"]),
            reference_marks=dict(result["raw_reference_marks"]),
            decision_reason=(
                "Received BASE ordering and causal H5 participation; K5 duplicates BASE exposure"
            ),
        ),
        received_scientific_component=result,
        normalized_field_mapping_only=True,
        runtime_K_rank_weight_recalculation=False,
    )


def receive(root, authority, *, clock):
    root = Path(root)
    folder = root / FOLDER
    child = folder / "BASE_STATE_BUDGET"
    if authority.get("task_id") != STATE or folder != folder.resolve():
        raise ValueError("wrong STATE scope")
    spec = authority["scientific_consumer"]
    names = dict(
        package=child / "current-package.json",
        final=child / "final-manifest.json",
        consumer=folder / "synthesis_consumer.py",
        manifest=folder / "implementation-manifest.json",
        schema=folder / "consumer-schema.json",
        contract=folder / "prospective-contract.json",
    )
    saved = {}
    for key, path in names.items():
        if Path(spec[key]["path"]) != path:
            raise ValueError("noncanonical STATE binding")
        saved[key] = bound_bytes(root, spec[key])
    receipt = authority["scientific_acceptance"]
    if Path(receipt["path"]) != folder / "independent-BASE_STATE_BUDGET-result-review.json":
        raise ValueError("wrong actual STATE review")
    review = json.loads(bound_bytes(root, receipt))
    package = json.loads(saved["package"])
    if (
        review.get("task_id") != STATE
        or review.get("reviewer") != REVIEWER
        or review.get("verdict") != "approve_result"
        or review.get("component_result_accepted") is not True
        or review.get("target") != spec["final"]
        or review.get("package") != spec["package"]
        or review.get("implementation") != spec["manifest"]
        or review.get("forecast") != package["forecast"]
    ):
        raise ValueError("current STATE result not accepted")
    bindings = json.loads(saved["manifest"])["files"]
    if spec["consumer"] not in bindings:
        raise ValueError("STATE consumer not in accepted code")
    for row in bindings:
        bound_bytes(root, row)
    sys.path.insert(0, str(folder))
    try:
        module = importlib.import_module("synthesis_consumer")
        if Path(module.__file__).resolve() != folder / "synthesis_consumer.py":
            raise ValueError("STATE module collision")
        result = module.receive_current_package(spec["package"]["path"], for_execution=True)
    finally:
        sys.path.remove(str(folder))
    if (
        result["review"] != receipt
        or result["package"] != spec["package"]
        or result["final"] != spec["final"]
        or result["forecast"] != package["forecast"]
        or not aware(clock()) < aware(result["consume_before"])
    ):
        raise ValueError("STATE returned receipt/clock mismatch")
    for key in names:
        if bound_bytes(root, spec[key]) != saved[key]:
            raise ValueError("STATE changed during reception")
    bound_bytes(root, receipt)
    for row in bindings:
        bound_bytes(root, row)
    return normalize_received(result)
