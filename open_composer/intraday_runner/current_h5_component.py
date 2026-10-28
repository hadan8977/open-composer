"""H5 component reception for the existing initialization runtime.

This adapter provides no account,
source, fit, inference, activation or scheduling operation. The exact public
scientific receiver remains responsible for its received model arithmetic.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

from open_composer.intraday_runner.current_initialization_controls import aware, number
from open_composer.intraday_runner.source_method_bindings import bound_bytes

TASK = "H5-LEARNED-SWING-PAPER-VALIDATION-20261019"
REVIEWER = "93af0483-230a-4632-8b48-c63cd53a01f7"
FOLDER = (
    "reports/research/program/owner-profit-delivery-plan-20261017/"
    "second-swing-learned-paper-20261019"
)


def normalize_received(result):
    """Adapt names only. Do not calculate K, rank, filter STOCK or reweight."""
    if (
        result.get("task_id") != TASK
        or result.get("capital_USD") != 10000
        or result.get("combined_cap_USD") != 20000
        or result.get("reference_day") != "2026-10-16"
        or result.get("operating_authority") is not False
        or result.get("targets_are_holdings_or_orders") is not False
    ):
        raise ValueError("H5 scientific/operating scope mismatch")
    symbols, weights = result["symbols"], result["weights"]
    if (
        len(symbols) != 31
        or len(set(symbols)) != 31
        or len(weights) != 31
        or "PBCT" in symbols
        or "MTB" in symbols
        or "RE" in symbols
        or "EG" not in symbols
        or type(result["K"]) is not int
        or not 0 <= result["K"] <= 5
    ):
        raise ValueError("H5 legal carrier/K interface mismatch")
    values = [number(w) for w in weights]
    if any(w not in {number(0), number(".2")} for w in values):
        raise ValueError("H5 fixed twenty-percent weights changed")
    if sum(w > 0 for w in values) != result["K"]:
        raise ValueError("received K and received weights disagree")
    for symbol, weight in zip(symbols, values, strict=True):
        if weight and number(result["raw_reference_marks"][symbol]) <= 0:
            raise ValueError("unreceived raw execution mark")
    return dict(
        forecast=dict(
            symbols=list(symbols),
            weights=list(weights),
            reference_marks=dict(result["raw_reference_marks"]),
            decision_reason=result["reason"],
        ),
        received_scientific_component=result,
        normalized_field_mapping_only=True,
        positive_STOCK_filter_or_K_recalculation=False,
    )


def receive(root, authority, *, clock):
    root = Path(root)
    folder = root / FOLDER
    if folder != folder.resolve():
        raise ValueError("aliased scientific root")
    if authority.get("task_id") != TASK:
        raise ValueError("wrong H5 authority task")
    spec = authority["scientific_consumer"]
    names = dict(
        package="current-package.json",
        manifest="implementation-manifest.json",
        final="final-manifest.json",
        schema="consumer-schema.json",
        repair="consumer-repair-manifest.json",
        consumer="h5_consumer_stdlib.py",
    )
    contents = {}
    for key, name in names.items():
        if Path(spec[key]["path"]) != folder / name:
            raise ValueError("noncanonical H5 reception path")
        contents[key] = bound_bytes(root, spec[key])
    receipt = authority["scientific_acceptance"]
    if Path(receipt["path"]) != folder / "independent-result-review.json":
        raise ValueError("wrong scientific result receipt")
    review = json.loads(bound_bytes(root, receipt))
    if (
        review.get("task_id") != TASK
        or review.get("reviewer") != REVIEWER
        or review.get("verdict") != "approve_result"
        or review.get("component_result_accepted") is not True
        or review.get("target") != spec["final"]
        or review.get("consumer_repair_accepted") is not True
        or review.get("consumer_repair") != spec["repair"]
    ):
        raise ValueError("actual H5 result not independently received")
    final = json.loads(contents["final"])
    if any(spec[key] not in final["files"] for key in ("package", "manifest", "schema")):
        raise ValueError("final seal does not bind exact H5 package/library/schema")
    bindings = json.loads(contents["manifest"])["files"]
    repair = json.loads(contents["repair"])
    if (
        repair.get("sealed_final") != spec["final"]
        or repair.get("sealed_package") != spec["package"]
        or repair.get("schema") != spec["schema"]
        or spec["consumer"] not in repair["files"]
    ):
        raise ValueError("accepted postseal H5 consumer repair differs")
    bindings = bindings + repair["files"]
    for row in bindings:
        bound_bytes(root, row)
    sys.path.insert(0, str(folder))
    try:
        module = importlib.import_module("h5_consumer_stdlib")
        if Path(module.__file__).resolve() != folder / "h5_consumer_stdlib.py":
            raise ValueError("H5 consumer module collision")
        result = module.receive_current_package(spec["package"]["path"], for_execution=True)
    finally:
        sys.path.remove(str(folder))
    if result["review"] != receipt or result["final"] != spec["final"]:
        raise ValueError("scientific receiver returned different acceptance")
    if not aware(clock()) < aware(result["consume_before"]):
        raise ValueError("current H5 instruction expired")
    for key in names:
        if bound_bytes(root, spec[key]) != contents[key]:
            raise ValueError("H5 reception bytes drifted")
    bound_bytes(root, receipt)
    for row in bindings:
        bound_bytes(root, row)
    return normalize_received(result)
