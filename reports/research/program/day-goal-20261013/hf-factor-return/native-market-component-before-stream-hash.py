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


def _load_binding(root: Path, binding: Any, name: str, blocked: list[str]) -> Any:
    if not isinstance(binding, dict) or not isinstance(binding.get("path"), str):
        blocked.append(f"market_component_{name}_binding_missing")
        return None
    path = root / binding["path"]
    if (
        not path.resolve().is_relative_to(root.resolve())
        or path.is_symlink()
        or not path.is_file()
        or hashlib.sha256(path.read_bytes()).hexdigest() != binding.get("sha256")
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
                        or hashlib.sha256(path.read_bytes()).hexdigest() != source.get("sha256")
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
