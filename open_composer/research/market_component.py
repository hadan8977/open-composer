"""Applicability for reviewed, nonpromotable market-component experiments.

Such experiments have real security timestamps but do not necessarily have a
StrategySpec implementation. Their scientific and implementation definitions
are bound directly; this route grants no trading or promotion readiness.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

MARKET_COMPONENT_ROLE = "market_component_method"
MARKET_COMPONENT_FALSE_FIELDS = (
    "promotion_eligible",
    "paper_trading_allowed",
    "broker_activity_allowed",
    "pit_universe_certified",
    "deployment_readiness_claim",
)


def _sha256_file(path: Path) -> str:
    """Verify large method input bindings without holding their full bytes in RAM."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_binding(root: Path, binding: Any, name: str, blocked: list[str]) -> Any:
    if not isinstance(binding, dict) or not isinstance(binding.get("path"), str):
        blocked.append(f"market_component_{name}_binding_missing")
        return None
    path = root / binding["path"]
    if (
        not path.resolve().is_relative_to(root.resolve())
        or path.is_symlink()
        or not path.is_file()
        or _sha256_file(path) != binding.get("sha256")
    ):
        blocked.append(f"market_component_{name}_binding_invalid")
        return None
    try:
        payload = json.loads(path.read_text())
    except (ValueError, UnicodeError):
        blocked.append(f"market_component_{name}_invalid_json")
        return None
    if not isinstance(payload, dict):
        blocked.append(f"market_component_{name}_not_object")
        return None
    return payload


def _review_binds(review: dict[str, Any], artifact: dict[str, Any]) -> bool:
    if not isinstance(artifact, dict):
        return False
    bindings = review.get("bindings")
    rows = list(bindings.values()) if isinstance(bindings, dict) else bindings
    return isinstance(rows, list) and any(
        isinstance(row, dict)
        and all(row.get(key) == artifact.get(key) for key in ("path", "sha256"))
        for row in rows
    )


def market_component_manifest_blockers(
    manifest: dict[str, Any], search: dict[str, Any], root: Path
) -> list[str]:
    blocked: list[str] = []
    if (
        manifest.get("research_role") != MARKET_COMPONENT_ROLE
        or search.get("research_role") != MARKET_COMPONENT_ROLE
        or manifest.get("schema_version") != 3
        or manifest.get("generated_before_backtest") is not True
        or manifest.get("manifest_type") != "generic_candidate_family_v1"
        or search.get("candidate_manifest_contract") != "generic_candidate_family_v1"
        or manifest.get("spec_hashes")
    ):
        blocked.append("market_component_manifest_role_invalid")
    candidates = manifest.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return [*blocked, "market_component_candidates_missing"]
    ids = [row.get("candidate_id") for row in candidates if isinstance(row, dict)]
    if len(ids) != len(candidates) or any(not isinstance(x, str) or not x for x in ids):
        return [*blocked, "market_component_candidate_ids_invalid"]
    if len(ids) != len(set(ids)):
        blocked.append("market_component_candidate_ids_duplicate")
    seen = set()
    for row in candidates:
        if (
            row.get("research_role") != MARKET_COMPONENT_ROLE
            or row.get("promotion_eligible") is not False
            or row.get("spec_path")
        ):
            blocked.append("market_component_candidate_scope_invalid")
        binding = {
            "path": row.get("method_definition_path"),
            "sha256": row.get("method_definition_sha256"),
        }
        if not all(isinstance(value, str) for value in binding.values()):
            blocked.append("market_component_definition_binding_invalid")
            continue
        identity = (binding["path"], binding["sha256"])
        if identity in seen:
            continue
        seen.add(identity)
        definition = _load_binding(root, binding, "definition", blocked)
        if definition is None:
            continue
        expected = {
            "schema_version": 1,
            "research_role": MARKET_COMPONENT_ROLE,
            "iter_id": search.get("iter_id"),
            "candidate_manifest_path": search.get("candidate_manifest_path"),
            "data_feasibility_path": search.get("data_feasibility_path"),
            "time_axis_kind": "market_timestamp",
            "claim_scope": "conditional_cohort",
            "real_market_claim": True,
            "candidate_ids": ids,
        }
        for key, value in expected.items():
            if definition.get(key) != value:
                blocked.append(f"market_component_definition_{key}_mismatch")
        for key in MARKET_COMPONENT_FALSE_FIELDS:
            if definition.get(key) is not False:
                blocked.append(f"market_component_definition_{key}_must_be_false")
        artifacts = {
            key: _load_binding(root, definition.get(key), key, blocked)
            for key in (
                "scientific_plan",
                "independent_plan_review",
                "implementation_manifest",
                "independent_implementation_review",
            )
        }
        for review_key, target_key, verdict in (
            ("independent_plan_review", "scientific_plan", "approve_deep_plan"),
            (
                "independent_implementation_review",
                "implementation_manifest",
                "approve_implementation",
            ),
        ):
            review = artifacts[review_key]
            if review is not None and (
                review.get("verdict") != verdict
                or not review.get("reviewer")
                or not review.get("author")
                or review["reviewer"] == review["author"]
                or not _review_binds(review, definition.get(target_key))
            ):
                blocked.append(f"market_component_{review_key}_not_independent_approved_bound")
        implementation = artifacts["implementation_manifest"]
        if implementation is not None:
            files = implementation.get("files")
            if not isinstance(files, list) or not files:
                blocked.append("market_component_implementation_files_missing")
            else:
                for source in files:
                    if not isinstance(source, dict) or not isinstance(source.get("path"), str):
                        blocked.append("market_component_implementation_file_binding_invalid")
                        continue
                    path = root / source["path"]
                    if (
                        not path.resolve().is_relative_to(root.resolve())
                        or path.is_symlink()
                        or not path.is_file()
                        or _sha256_file(path) != source.get("sha256")
                    ):
                        blocked.append("market_component_implementation_file_binding_invalid")
    return blocked


def market_component_role_blockers(external: Any, search: Any, root: Path) -> list[str]:
    payloads = (external, search)
    if not any(
        isinstance(row, dict) and row.get("research_role") == MARKET_COMPONENT_ROLE
        for row in payloads
    ):
        return []
    if any(
        not isinstance(row, dict)
        or row.get("research_role") != MARKET_COMPONENT_ROLE
        or row.get("schema_version") != 3
        or row.get("source_spec_path")
        or row.get("spec_hash")
        for row in payloads
    ):
        return ["market_component_dossier_role_invalid"]
    blocked: list[str] = []
    expected = f"reports/research/iterations/{search.get('iter_id')}/candidate-manifest.json"
    if search.get("candidate_manifest_path") != expected:
        blocked.append("market_component_noncanonical_manifest")
    manifest = _load_binding(
        root,
        {
            "path": search.get("candidate_manifest_path"),
            "sha256": search.get("candidate_manifest_sha256"),
        },
        "manifest",
        blocked,
    )
    if manifest is not None:
        blocked.extend(market_component_manifest_blockers(manifest, search, root))
    return blocked


def market_component_role_applies(iteration_dir: Path, root: Path) -> bool:
    try:
        external = json.loads((iteration_dir / "external-brief.json").read_text())
        search = json.loads((iteration_dir / "search-space.json").read_text())
    except (OSError, ValueError):
        return False
    return bool(
        isinstance(external, dict)
        and external.get("research_role") == MARKET_COMPONENT_ROLE
        and not market_component_role_blockers(external, search, root)
    )


FIXED_COMPARISON_OPERATION_FIELDS = (
    "new_family_discovery",
    "adaptive_selection",
    "candidate_pruning",
    "parameter_optimization",
    "new_model_fits",
    "new_model_selection",
    "promotion_eligible",
)
FIXED_COMPARISON_TOP_WIRING_FIELDS = frozenset(
    (
        "schema_version",
        "iter_id",
        "research_role",
        "strategy_name",
        "source_spec_path",
        "spec_hash",
        "candidate_count",
        "candidates",
        "manifest_type",
        "generated_before_backtest",
        "generated_at",
        "spec_hashes",
        "contracts",
        "approved_candidate_proposal",
        "new_financial_trials",
    )
)
FIXED_COMPARISON_ROW_WIRING_FIELDS = frozenset(
    (
        "path",
        "role",
        "method",
        "ablation",
        "fallback",
        "mechanism_family",
        "mechanism",
        "scale_curve_point",
        "data_contract",
        "feature_contract",
        "label_contract",
        "validation_contract",
        "cost_contract",
        "benchmark_contract",
    )
)


def _inactive_operation(value: Any) -> bool:
    # bool is an int subclass. Floats, strings and other false-like values
    # cannot silently certify absence of training or selection.
    return value is None or value is False or (type(value) is int and value == 0)


def _same_json_definition(actual: Any, approved: Any) -> bool:
    return json.dumps(actual, sort_keys=True, allow_nan=False) == json.dumps(
        approved, sort_keys=True, allow_nan=False
    )


def _canonical_fixed_comparison_matches(manifest, approved, scope, search, approved_binding):
    candidates, planned_rows = manifest["candidates"], approved["candidates"]
    for payload in (search, manifest, *candidates, *planned_rows):
        if any(
            not _inactive_operation(payload.get(key)) for key in FIXED_COMPARISON_OPERATION_FIELDS
        ):
            return False
    wiring = scope.get("canonical_wiring", {})
    if not isinstance(wiring, dict) or set(wiring) - {"manifest", "candidates"}:
        return False
    top, rows = wiring.get("manifest", {}), wiring.get("candidates", {})
    if not isinstance(top, dict) or not isinstance(rows, dict):
        return False
    if set(top) - (FIXED_COMPARISON_TOP_WIRING_FIELDS - {"candidates"}):
        return False
    if set(rows) - {r["candidate_id"] for r in candidates}:
        return False
    # Known native metadata has its own typed semantics. Any other scientific
    # top-level key must already occur, unchanged, in the approved inventory.
    for key, value in manifest.items():
        if key in FIXED_COMPARISON_OPERATION_FIELDS or key == "candidates":
            continue
        if key not in FIXED_COMPARISON_TOP_WIRING_FIELDS:
            if key not in approved or not _same_json_definition(value, approved[key]):
                return False
        elif key in top and not _same_json_definition(value, top[key]):
            return False
    if any(key not in manifest for key in top):
        return False
    if type(manifest.get("candidate_count")) is not int or manifest["candidate_count"] != len(
        candidates
    ):
        return False
    if manifest.get("iter_id") != search.get("iter_id"):
        return False
    for key in ("contracts", "spec_hashes"):
        if key in manifest and not isinstance(manifest[key], dict):
            return False
    for key in ("strategy_name", "generated_at"):
        if key in manifest and not isinstance(manifest[key], str):
            return False
    if "new_financial_trials" in manifest and (
        type(manifest["new_financial_trials"]) is not int or manifest["new_financial_trials"] < 0
    ):
        return False
    if "approved_candidate_proposal" in manifest and not _same_json_definition(
        manifest["approved_candidate_proposal"], approved_binding
    ):
        return False
    for actual, planned in zip(candidates, planned_rows, strict=True):
        if any(
            key not in actual or not _same_json_definition(actual[key], value)
            for key, value in planned.items()
        ):
            return False
        extra_wiring = rows.get(actual["candidate_id"], {})
        if (
            not isinstance(extra_wiring, dict)
            or set(extra_wiring) - FIXED_COMPARISON_ROW_WIRING_FIELDS
        ):
            return False
        if any(
            key not in actual or not _same_json_definition(actual[key], value)
            for key, value in extra_wiring.items()
        ):
            return False
        for key in set(actual) - set(planned) - set(FIXED_COMPARISON_OPERATION_FIELDS):
            if key in ("method_definition_path", "method_definition_sha256"):
                continue  # Exact binding already checked by the original component role gate.
            if key not in FIXED_COMPARISON_ROW_WIRING_FIELDS or key not in extra_wiring:
                return False
    return True


def fixed_seen_component_comparison_applies(search: Any, root: Path) -> bool:
    """A verified fixed continuation is not new family discovery.

    This only classifies campaign applicability. Independent reviews and their
    exact plan, inventory, code and input bindings remain mandatory; the ordinary
    source, knowledge, cost, validation and execution gates still run.
    """
    try:
        return _fixed_seen_component_comparison_applies(search, root)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def _fixed_seen_component_comparison_applies(search: Any, root: Path) -> bool:
    if not isinstance(search, dict) or search.get("research_role") != MARKET_COMPONENT_ROLE:
        return False
    directory = root / "reports/research/iterations" / str(search.get("iter_id") or "")
    if not directory.resolve().is_relative_to(root.resolve()) or directory.is_symlink():
        return False
    current_search = json.loads((directory / "search-space.json").read_text())
    external = json.loads((directory / "external-brief.json").read_text())
    if current_search != search or market_component_role_blockers(external, search, root):
        return False
    blocked: list[str] = []
    manifest = _load_binding(
        root,
        {"path": search["candidate_manifest_path"], "sha256": search["candidate_manifest_sha256"]},
        "manifest",
        blocked,
    )
    candidates = manifest["candidates"]
    definitions = {(r["method_definition_path"], r["method_definition_sha256"]) for r in candidates}
    if len(definitions) != 1:
        return False
    path, digest = next(iter(definitions))
    definition = _load_binding(root, {"path": path, "sha256": digest}, "definition", blocked)
    plan = _load_binding(root, definition["scientific_plan"], "scientific_plan", blocked)
    plan_review = _load_binding(
        root, definition["independent_plan_review"], "independent_plan_review", blocked
    )
    full_plan = plan.get("full_definition")
    if not isinstance(full_plan, dict) or not _review_binds(plan_review, full_plan):
        return False
    full_path = root / full_plan["path"]
    if (
        not full_path.resolve().is_relative_to(root.resolve())
        or full_path.is_symlink()
        or not full_path.is_file()
        or _sha256_file(full_path) != full_plan.get("sha256")
    ):
        return False
    implementation = _load_binding(
        root, definition["implementation_manifest"], "implementation_manifest", blocked
    )
    review = _load_binding(
        root,
        definition["independent_implementation_review"],
        "independent_implementation_review",
        blocked,
    )
    scope_binding = implementation.get("fixed_component_comparison")
    scope = _load_binding(root, scope_binding, "fixed_comparison", blocked)
    if not scope or not _review_binds(review, scope_binding):
        return False
    # The reviewer signs the exact rendered input/inventory scope as well as
    # implementation code. A role name or unreviewed boolean cannot grant this.
    if (
        scope.get("schema_version") != 1
        or scope.get("iter_id") != search.get("iter_id")
        or scope.get("scientific_plan") != definition["scientific_plan"]
        or implementation.get("scientific_plan") != definition["scientific_plan"]
        or scope.get("operations") != ["compare_all_fixed_candidates"]
    ):
        return False
    if any(
        scope.get(key) is not False or not _inactive_operation(search.get(key))
        for key in FIXED_COMPARISON_OPERATION_FIELDS
    ):
        return False
    approved_binding = plan.get("candidate_manifest")
    if scope.get("approved_inventory") != approved_binding:
        return False
    approved = _load_binding(root, approved_binding, "approved_inventory", blocked)
    validation = plan.get("validation")
    if (
        not isinstance(validation, dict)
        or validation.get("all_windows_seen") is not True
        or validation.get("untouched_OOS") is not False
        or scope.get("validation") != validation
    ):
        return False
    parent = plan.get("parent_task")
    if not parent or approved.get("parent_task") != parent or scope.get("parent_task") != parent:
        return False
    planned_rows = approved.get("candidates")
    if not isinstance(planned_rows, list) or len(planned_rows) != len(candidates):
        return False
    ids = [r["candidate_id"] for r in candidates]
    if scope.get("candidate_ids") != ids or [r.get("candidate_id") for r in planned_rows] != ids:
        return False
    if any(planned.get("promotion_eligible") is not False for planned in planned_rows):
        return False
    if not _canonical_fixed_comparison_matches(
        manifest,
        approved,
        scope,
        search,
        approved_binding,
    ):
        return False
    if (
        approved.get("new_model_fits") != 0
        or scope.get("search_definition")
        != {key: search.get(key) for key in ("paths", "total_candidate_budget")}
        or search.get("total_candidate_budget") != len(candidates)
    ):
        return False
    input_binding = implementation.get("actual_input_manifest")
    if scope.get("actual_input_manifest") != input_binding:
        return False
    inputs = _load_binding(root, input_binding, "actual_inputs", blocked)
    inventory = inputs.get("actual_financial_read_inputs")
    if (
        not isinstance(inventory, list)
        or not inventory
        or scope.get("actual_input_inventory") != inventory
    ):
        return False
    if scope.get("inherited_source_inputs") != inputs.get("original_source_inputs"):
        return False
    for key in ("inherited_source_acceptance", "inherited_full_result_acceptance"):
        if (
            scope.get(key) != inputs.get(key)
            or _load_binding(root, inputs.get(key), key, blocked) is None
        ):
            return False
    files = implementation.get("files", [])
    # Every actual read input must be in the independently approved implementation
    # inventory. Its actual bytes are already verified by the component role gate.
    if any(
        not any(all(source.get(k) == row.get(k) for k in ("path", "sha256")) for source in files)
        for row in inventory
    ):
        return False
    return not blocked
