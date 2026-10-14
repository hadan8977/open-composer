"""Synthetic governance trees, not actual financial admission or model selection."""

import copy
import json

import pytest

from open_composer.research.iteration_dossier import _campaign_contract_blockers
from open_composer.research.market_component import fixed_seen_component_comparison_applies
from tests.test_market_component import _market_fixture
from tests.test_public_method_replication import _binding, _write


def reseal(root, fixture, sign_scope=True):
    directory, external, search, manifest, definition = fixture
    implementation = directory / "implementation-manifest.json"
    scope = directory / "fixed-comparison.json"
    payload = json.loads(implementation.read_text())
    payload["fixed_component_comparison"] = _binding(root, scope)
    _write(implementation, payload)
    review = directory / "implementation-review.json"
    _write(
        review,
        {
            "verdict": "approve_implementation",
            "author": "synthetic-author",
            "reviewer": "synthetic-independent",
            "bindings": [_binding(root, implementation)]
            + ([_binding(root, scope)] if sign_scope else []),
        },
    )
    definition["implementation_manifest"] = _binding(root, implementation)
    definition["independent_implementation_review"] = _binding(root, review)
    _write(directory / "method-definition.json", definition)
    for row in manifest["candidates"]:
        row["method_definition_sha256"] = _binding(root, directory / "method-definition.json")[
            "sha256"
        ]
    _write(directory / "candidate-manifest.json", manifest)
    search["candidate_manifest_sha256"] = _binding(root, directory / "candidate-manifest.json")[
        "sha256"
    ]
    _write(directory / "search-space.json", search)
    _write(directory / "external-brief.json", external)


def fixed_fixture(root):
    fixture = _market_fixture(root)
    directory, _, search, manifest, definition = fixture
    base = manifest["candidates"][0]
    rows = []
    for i in range(60):
        row = copy.deepcopy(base)
        row.update(candidate_id=f"M{i + 1:02d}", path=f"policy{i // 20}")
        rows.append(row)
    manifest["candidates"] = rows
    manifest["candidate_count"] = 60
    definition["candidate_ids"] = [r["candidate_id"] for r in rows]
    search.update(
        created_at="2026-10-14T12:00:00Z",
        total_candidate_budget=60,
        paths=[{"name": f"policy{i}", "candidate_count": 20} for i in range(3)],
    )
    plan_path = root / definition["scientific_plan"]["path"]
    review_path = root / definition["independent_plan_review"]["path"]
    planned = [
        {
            k: v
            for k, v in r.items()
            if k not in ("method_definition_sha256", "method_definition_path")
        }
        for r in rows
    ]
    proposal = directory / "approved-inventory.json"
    _write(
        proposal,
        {"parent_task": "synthetic-existing-parent", "new_model_fits": 0, "candidates": planned},
    )
    md = directory / "plan.md"
    md.write_text("Synthetic governance fixture: all fixed existing output comparisons.\n")
    validation = {"all_windows_seen": True, "untouched_OOS": False}
    _write(
        plan_path,
        {
            "parent_task": "synthetic-existing-parent",
            "candidate_manifest": _binding(root, proposal),
            "full_definition": _binding(root, md),
            "validation": validation,
        },
    )
    _write(
        review_path,
        {
            "author": "synthetic-author",
            "reviewer": "synthetic-independent",
            "verdict": "approve_deep_plan",
            "bindings": [_binding(root, plan_path), _binding(root, md)],
        },
    )
    definition["scientific_plan"] = _binding(root, plan_path)
    definition["independent_plan_review"] = _binding(root, review_path)
    read = directory / "read-input.json"
    _write(read, {"existing_synthetic_output": True})
    prior = directory / "prior-acceptance.json"
    _write(prior, {"synthetic_governance_fixture": True})
    inputs = directory / "inputs.json"
    inventory = [_binding(root, read)]
    _write(
        inputs,
        {
            "actual_financial_read_inputs": inventory,
            "original_source_inputs": inventory,
            "inherited_source_acceptance": _binding(root, prior),
            "inherited_full_result_acceptance": _binding(root, prior),
        },
    )
    scope = {
        "schema_version": 1,
        "iter_id": directory.name,
        "parent_task": "synthetic-existing-parent",
        "scientific_plan": _binding(root, plan_path),
        "approved_inventory": _binding(root, proposal),
        "validation": validation,
        "candidate_ids": definition["candidate_ids"],
        "operations": ["compare_all_fixed_candidates"],
        "search_definition": {k: search[k] for k in ("paths", "total_candidate_budget")},
        "actual_input_manifest": _binding(root, inputs),
        "actual_input_inventory": inventory,
        "inherited_source_inputs": inventory,
        "inherited_source_acceptance": _binding(root, prior),
        "inherited_full_result_acceptance": _binding(root, prior),
    }
    for key in (
        "new_family_discovery",
        "adaptive_selection",
        "candidate_pruning",
        "parameter_optimization",
        "new_model_fits",
        "new_model_selection",
        "promotion_eligible",
    ):
        scope[key] = False
    _write(directory / "fixed-comparison.json", scope)
    implementation = directory / "implementation-manifest.json"
    old = json.loads(implementation.read_text())
    old.update(
        scientific_plan=_binding(root, plan_path), actual_input_manifest=_binding(root, inputs)
    )
    old["files"].extend([_binding(root, inputs), _binding(root, read)])
    _write(implementation, old)
    reseal(root, fixture)
    return fixture


def test_sixty_fixed_seen_reviewed_rows_use_scope_classification_and_keep_inventory(tmp_path):
    directory, _, search, manifest, _ = fixed_fixture(tmp_path)
    assert len(manifest["candidates"]) == 60 and len(search["paths"]) == 3
    assert fixed_seen_component_comparison_applies(search, tmp_path)
    blocked = _campaign_contract_blockers(search, tmp_path, stage="pre-discovery")
    assert blocked == ["warning:reviewed_fixed_seen_component_campaign_not_applicable"]
    assert len(json.loads((directory / "candidate-manifest.json").read_text())["candidates"]) == 60


@pytest.mark.parametrize(
    "mutation",
    [
        "self_flag_only",
        "ordinary_strategy",
        "missing_plan_review",
        "same_reviewer",
        "revise_implementation",
        "scope_not_signed",
        "input_manifest_changed",
        "input_bytes_changed",
        "new_family_discovery",
        "adaptive_selection",
        "candidate_pruning",
        "parameter_optimization",
        "new_model_fits",
        "new_model_selection",
        "promotion_eligible",
        "unseen",
        "changed_policy",
        "inventory_deleted",
        "stale_scope_inventory",
        "registered_child",
        "registered_bound",
        "plan_md_changed",
    ],
)
def test_ordinary_or_unverified_or_changed_scopes_keep_campaign_gate(tmp_path, mutation):
    fixture = fixed_fixture(tmp_path)
    directory, external, search, manifest, definition = fixture
    scope_path = directory / "fixed-comparison.json"
    scope = json.loads(scope_path.read_text())
    if mutation in (
        "new_family_discovery",
        "adaptive_selection",
        "candidate_pruning",
        "parameter_optimization",
        "new_model_fits",
        "new_model_selection",
        "promotion_eligible",
    ):
        scope[mutation] = True
        _write(scope_path, scope)
        reseal(tmp_path, fixture)
    elif mutation == "unseen":
        scope["validation"]["untouched_OOS"] = True
        _write(scope_path, scope)
        reseal(tmp_path, fixture)
    elif mutation == "scope_not_signed":
        reseal(tmp_path, fixture, sign_scope=False)
    elif mutation in ("self_flag_only", "ordinary_strategy"):
        search["verified_fixed_component"] = True
        if mutation == "ordinary_strategy":
            search["research_role"] = "strategy"
        else:
            (directory / "fixed-comparison.json").unlink()
        _write(directory / "search-space.json", search)
    elif mutation == "missing_plan_review":
        (tmp_path / definition["independent_plan_review"]["path"]).unlink()
    elif mutation in ("same_reviewer", "revise_implementation"):
        path = directory / "implementation-review.json"
        payload = json.loads(path.read_text())
        if mutation == "same_reviewer":
            payload["reviewer"] = payload["author"]
        else:
            payload["verdict"] = "revise_implementation"
        _write(path, payload)
        definition["independent_implementation_review"] = _binding(tmp_path, path)
        _write(directory / "method-definition.json", definition)
        for row in manifest["candidates"]:
            row["method_definition_sha256"] = _binding(
                tmp_path, directory / "method-definition.json"
            )["sha256"]
        _write(directory / "candidate-manifest.json", manifest)
        search["candidate_manifest_sha256"] = _binding(
            tmp_path, directory / "candidate-manifest.json"
        )["sha256"]
        _write(directory / "search-space.json", search)
    elif mutation == "input_manifest_changed":
        (directory / "inputs.json").write_text("{}")
    elif mutation == "input_bytes_changed":
        (directory / "read-input.json").write_text("changed")
    elif mutation == "plan_md_changed":
        (directory / "plan.md").write_text("changed scientific definition")
    elif mutation in ("changed_policy", "inventory_deleted"):
        if mutation == "changed_policy":
            manifest["candidates"][0]["method"] = "changed method"
        else:
            manifest["candidates"].pop()
        reseal(tmp_path, fixture)
    elif mutation == "stale_scope_inventory":
        scope["actual_input_inventory"] = []
        _write(scope_path, scope)
        reseal(tmp_path, fixture)
    else:
        _write(
            tmp_path / "reports/research/campaigns/registered/research-campaign-contract.json",
            {"campaign_id": "registered", "child_iteration_ids": [directory.name]},
        )
        if mutation == "registered_bound":
            search.update(
                campaign_id="registered",
                campaign_contract_path="reports/research/campaigns/registered/research-campaign-contract.json",
                campaign_contract_sha256=_binding(
                    tmp_path,
                    tmp_path
                    / "reports/research/campaigns/registered/research-campaign-contract.json",
                )["sha256"],
            )
    blocked = _campaign_contract_blockers(search, tmp_path, stage="pre-discovery")
    assert "warning:reviewed_fixed_seen_component_campaign_not_applicable" not in blocked
    assert any(not item.startswith("warning:") for item in blocked)
    if mutation == "registered_child":
        assert "campaign_contract_binding_missing_for_registered_child:registered" in blocked
