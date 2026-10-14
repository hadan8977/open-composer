from __future__ import annotations

import json
from pathlib import Path

import pytest

from open_composer.research.iteration_dossier import (
    _candidate_manifest_blockers,
    _external_brief_blockers,
    public_method_role_applies,
)
from open_composer.research.knowledge_memory import assess_iteration_knowledge
from open_composer.research.market_component import (
    MARKET_COMPONENT_ROLE,
    market_component_role_applies,
    market_component_role_blockers,
)
from tests.test_public_method_replication import _binding, _fixture, _write


def _market_fixture(root: Path):
    directory, external, search, manifest, definition = _fixture(root)
    for payload in (external, search, manifest, definition, manifest["candidates"][0]):
        payload["research_role"] = MARKET_COMPONENT_ROLE
    definition.update(
        time_axis_kind="market_timestamp",
        claim_scope="conditional_cohort",
        real_market_claim=True,
        pit_universe_certified=False,
        deployment_readiness_claim=False,
    )
    implementation = directory / "implementation-manifest.json"
    _write(implementation, {"files": [_binding(root, directory / "official-implementation.py")]})
    review = directory / "implementation-review.json"
    _write(
        review,
        {
            "verdict": "approve_implementation",
            "author": "method-author",
            "reviewer": "root",
            "bindings": [_binding(root, implementation)],
        },
    )
    definition["implementation_manifest"] = _binding(root, implementation)
    definition["independent_implementation_review"] = _binding(root, review)
    _write(directory / "method-definition.json", definition)
    manifest["candidates"][0]["method_definition_sha256"] = _binding(
        root, directory / "method-definition.json"
    )["sha256"]
    _write(directory / "candidate-manifest.json", manifest)
    search["candidate_manifest_sha256"] = _binding(root, directory / "candidate-manifest.json")[
        "sha256"
    ]
    _write(directory / "search-space.json", search)
    _write(directory / "external-brief.json", external)
    return directory, external, search, manifest, definition


def test_named_market_component_is_not_relabelled_anonymous(tmp_path: Path):
    directory, external, search, _, _ = _market_fixture(tmp_path)
    assert market_component_role_applies(directory, tmp_path)
    assert not public_method_role_applies(directory, tmp_path)
    assert _external_brief_blockers(external, market_component=True) == []
    assert (
        _candidate_manifest_blockers(
            directory / "candidate-manifest.json", search, tmp_path, expected_total=1
        )
        == []
    )
    knowledge = assess_iteration_knowledge(directory.name, tmp_path).payload
    assert knowledge["market_component_role_applicable"]
    assert not knowledge["public_method_role_applicable"]
    assert "knowledge_scout_missing" in knowledge["blocked"]


@pytest.mark.parametrize(
    "mutation",
    [
        "promotion",
        "paper",
        "pit",
        "scope",
        "clock",
        "unreviewed",
        "same_author",
        "unbound_review",
        "code_changed",
        "mixed_role",
        "unbound_definition",
        "cost_changed",
    ],
)
def test_component_scope_and_causal_definition_remain_bound(tmp_path: Path, mutation: str):
    directory, external, search, manifest, definition = _market_fixture(tmp_path)
    if mutation in {"promotion", "paper", "pit", "scope", "clock"}:
        key, value = {
            "promotion": ("promotion_eligible", True),
            "paper": ("paper_trading_allowed", True),
            "pit": ("pit_universe_certified", True),
            "scope": ("claim_scope", "whole_account_alpha"),
            "clock": ("time_axis_kind", "sample_index"),
        }[mutation]
        definition[key] = value
    elif mutation in {"unreviewed", "same_author", "unbound_review"}:
        path = directory / "implementation-review.json"
        review = json.loads(path.read_text())
        if mutation == "unreviewed":
            review["verdict"] = "revise_implementation"
        elif mutation == "same_author":
            review["reviewer"] = review["author"]
        else:
            review["bindings"] = []
        _write(path, review)
        definition["independent_implementation_review"] = _binding(tmp_path, path)
    elif mutation == "code_changed":
        (directory / "official-implementation.py").write_text("changed")
    elif mutation == "mixed_role":
        manifest["candidates"][0]["research_role"] = "public_method_replication"
    elif mutation == "unbound_definition":
        definition.pop("scientific_plan")
    else:
        (directory / "costs.json").write_text("changed")
    _write(directory / "method-definition.json", definition)
    manifest["candidates"][0]["method_definition_sha256"] = _binding(
        tmp_path, directory / "method-definition.json"
    )["sha256"]
    _write(directory / "candidate-manifest.json", manifest)
    search["candidate_manifest_sha256"] = _binding(tmp_path, directory / "candidate-manifest.json")[
        "sha256"
    ]
    if mutation == "cost_changed":
        assert _candidate_manifest_blockers(
            directory / "candidate-manifest.json", search, tmp_path, expected_total=1
        )
    else:
        assert market_component_role_blockers(external, search, tmp_path)


def test_reviewed_component_reuses_fresh_sources_without_manufacturing_novelty(tmp_path: Path):
    directory, _, _, _, _ = _market_fixture(tmp_path)
    cards = tmp_path / "reports/harness/source_cards/method-fixture.jsonl"
    prior_cards = cards.with_name("prior-method-fixture.jsonl")
    rows = [json.loads(line) for line in cards.read_text().splitlines()]
    for row in rows:
        row["iteration_id"] = "prior_source_work"
    prior_cards.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    query = directory / "knowledge-scout-queries.json"
    baseline = directory / "knowledge-baseline.json"
    _write(query, {"curated_candidates": [], "queries": []})
    _write(baseline, {"synthetic_governance_fixture": True})
    _write(
        directory / "knowledge-scout.json",
        {
            "schema_version": 1,
            "iter_id": directory.name,
            "query_manifest_sha256": _binding(tmp_path, query)["sha256"],
            "baseline_sha256": _binding(tmp_path, baseline)["sha256"],
            "candidate_count": 0,
            "candidates": [],
        },
    )
    actual = assess_iteration_knowledge(directory.name, tmp_path).payload
    assert actual["counts"]["reused"] == 2
    assert actual["counts"]["new"] == 0
    assert actual["status"] == "ok"
    assert actual["novelty_policy"]["reviewed_method_fresh_source_reuse"]

    # Losing the bound independent approval must remove the scope-based reuse exception.
    (directory / "independent-review.json").write_text('{"verdict":"revise_plan"}')
    invalid = assess_iteration_knowledge(directory.name, tmp_path).payload
    assert not invalid["novelty_policy"]["reviewed_method_fresh_source_reuse"]
    assert "knowledge_no_new_or_refresh_evidence" in invalid["blocked"]
