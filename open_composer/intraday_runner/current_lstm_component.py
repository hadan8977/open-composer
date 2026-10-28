"""Receive one accepted temporal-model package for the existing paper runner.

No fitting, inference, source access, model selection or weight changes here.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

from open_composer.intraday_runner.current_initialization_controls import aware, number
from open_composer.intraday_runner.source_method_bindings import bound_bytes

TASK = "CROSS-ASSET-LSTM-PAPER-VALIDATION-20261019"
REVIEWER = "93af0483-230a-4632-8b48-c63cd53a01f7"
FOLDER = (
    "reports/research/program/owner-profit-delivery-plan-20261017/second-learned-paper-20261019"
)
SYMBOLS = ["SPY", "QQQ", "IWM", "EFA", "EEM", "IEF", "TLT", "GLD", "DBC", "UUP"]


def normalize_received(result):
    weights = [number(x) for x in result["weights"]]
    epsilon = number(".000000000001")
    if (
        result.get("task_id") != TASK
        or result.get("capital_USD") != 4000
        or result.get("combined_cap_USD") != 20000
        or result.get("reference_day") != "2026-10-16"
        or result.get("paper_ready") is not False
        or result.get("symbols") != SYMBOLS
        or len(weights) != 10
        or any(x > number(".2") + epsilon for x in weights)
        or sum(weights) > 1 + epsilon
        or abs(number(result["target_cash_weight"], nonnegative=False) - (1 - sum(weights)))
        > epsilon
        or result.get("dispatch_window") != ["2026-10-19T13:40:00Z", "2026-10-19T13:41:00Z"]
        or result.get("consume_before") != "2026-10-19T13:41:00Z"
        or result.get("holding_authority_cap") != "2026-11-14T00:00:00Z"
    ):
        raise ValueError("exact temporal-model operating interface differs")
    for symbol in SYMBOLS:
        if number(result["raw_reference_marks"][symbol]) <= 0:
            raise ValueError("missing completed-session raw reference")
    return dict(
        forecast=dict(
            symbols=list(result["symbols"]),
            weights=list(result["weights"]),
            reference_marks=dict(result["raw_reference_marks"]),
            decision_reason="Received fixed two-seed temporal controller; targets are not fills",
        ),
        received_scientific_component=result,
        normalized_field_mapping_only=True,
        weight_clipping_ranking_or_model_recalculation=False,
    )


def receive(root, authority, *, clock):
    root = Path(root)
    folder = root / FOLDER
    if folder != folder.resolve() or authority.get("task_id") != TASK:
        raise ValueError("wrong or aliased temporal-model scope")
    spec = authority["scientific_consumer"]
    names = dict(
        package="current-package.json",
        manifest="implementation-manifest.json",
        final="final-manifest.json",
        schema="consumer-schema.json",
        consumer="lstm_consumer.py",
        contract="prospective-contract.json",
        policy_interface="policy-interface.json",
    )
    contents = {}
    for key, name in names.items():
        if Path(spec[key]["path"]) != folder / name:
            raise ValueError("noncanonical temporal-model binding")
        contents[key] = bound_bytes(root, spec[key])
    receipt = authority["scientific_acceptance"]
    if Path(receipt["path"]) != folder / "independent-result-review.json":
        raise ValueError("wrong actual scientific result review")
    review = json.loads(bound_bytes(root, receipt))
    package = json.loads(contents["package"])
    if (
        review.get("task_id") != TASK
        or review.get("reviewer") != REVIEWER
        or review.get("verdict") != "approve_result"
        or review.get("component_result_accepted") is not True
        or review.get("target") != spec["final"]
        or review.get("package") != spec["package"]
        or review.get("implementation") != spec["manifest"]
        or review.get("forecast") != package["forecast"]
    ):
        raise ValueError("actual current temporal-model result not accepted")
    final = json.loads(contents["final"])
    if any(spec[key] not in final["files"] for key in names if key != "final"):
        raise ValueError("final seal does not bind the exact consumer interface")
    bindings = json.loads(contents["manifest"])["files"]
    if spec["consumer"] not in bindings:
        raise ValueError("consumer outside accepted implementation")
    for row in bindings:
        bound_bytes(root, row)
    sys.path.insert(0, str(folder))
    try:
        module = importlib.import_module("lstm_consumer")
        if Path(module.__file__).resolve() != folder / "lstm_consumer.py":
            raise ValueError("scientific module collision")
        result = module.receive_current_package(spec["package"]["path"], for_execution=True)
    finally:
        sys.path.remove(str(folder))
    if (
        result["independent_result_review"] != receipt
        or result["implementation"] != spec["manifest"]
        or result["forecast"] != package["forecast"]
    ):
        raise ValueError("returned acceptance differs from bound package")
    if not aware(clock()) < aware(result["consume_before"]):
        raise ValueError("current model instruction expired")
    for key in names:
        if bound_bytes(root, spec[key]) != contents[key]:
            raise ValueError("scientific bytes changed during reception")
    bound_bytes(root, receipt)
    for row in bindings:
        bound_bytes(root, row)
    return normalize_received(result)
