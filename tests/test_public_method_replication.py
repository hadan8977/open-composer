from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from open_composer.research.iteration_dossier import (
    PUBLIC_METHOD_ROLE,
    _candidate_manifest_blockers,
    _external_brief_blockers,
    _final_evaluation_receipt_blockers,
    _public_method_role_blockers,
    iteration_dossier_paths,
    public_method_role_applies,
)
from open_composer.research.knowledge_memory import assess_iteration_knowledge, claim_fingerprint


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _binding(root: Path, path: Path) -> dict[str, str]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _fixture(root: Path) -> tuple[Path, dict, dict, dict, dict]:
    iter_id = "t20261011_public_method_fixture"
    directory = root / "reports/research/iterations" / iter_id
    directory.mkdir(parents=True)
    implementation = directory / "official-implementation.py"
    implementation.write_text("# Synthetic governance fixture; never executed.\n")
    plan_path = directory / "scientific-plan.json"
    _write(plan_path, {"evidence": {"source_bindings": [_binding(root, implementation)]}})
    review_path = directory / "independent-review.json"
    _write(
        review_path,
        {
            "verdict": "approve_deep_plan",
            "reviewer": "independent",
            "author": "author",
            "bindings": {"plan": _binding(root, plan_path)},
        },
    )
    manifest_path = directory / "candidate-manifest.json"
    feasibility_path = directory / "data-feasibility.json"
    definition_path = directory / "method-definition.json"
    definition = {
        "schema_version": 1,
        "research_role": PUBLIC_METHOD_ROLE,
        "iter_id": iter_id,
        "candidate_manifest_path": manifest_path.relative_to(root).as_posix(),
        "data_feasibility_path": feasibility_path.relative_to(root).as_posix(),
        "time_axis_kind": "sample_index",
        "candidate_ids": ["M01"],
        "promotion_eligible": False,
        "paper_trading_allowed": False,
        "broker_activity_allowed": False,
        "real_market_claim": False,
        "scientific_plan": _binding(root, plan_path),
        "independent_plan_review": _binding(root, review_path),
        "author_implementation": _binding(root, implementation),
    }
    _write(definition_path, definition)
    contracts = {}
    candidate = {
        "candidate_id": "M01",
        "path": "method",
        "role": "anchor",
        "method": "original",
        "ablation": "none",
        "fallback": "zero",
        "research_role": PUBLIC_METHOD_ROLE,
        "promotion_eligible": False,
        "method_definition_path": definition_path.relative_to(root).as_posix(),
        "method_definition_sha256": _binding(root, definition_path)["sha256"],
    }
    for group, field in (
        ("data", "data"),
        ("features", "feature"),
        ("labels", "label"),
        ("validation", "validation"),
        ("costs", "cost"),
        ("benchmarks", "benchmark"),
    ):
        path = directory / f"{group}.json"
        _write(path, {"contract_id": group, "synthetic_governance_fixture": True})
        contracts[group] = {group: _binding(root, path)}
        candidate[f"{field}_contract"] = group
    manifest = {
        "schema_version": 3,
        "research_role": PUBLIC_METHOD_ROLE,
        "manifest_type": "generic_candidate_family_v1",
        "iter_id": iter_id,
        "generated_before_backtest": True,
        "candidate_count": 1,
        "contracts": contracts,
        "candidates": [candidate],
    }
    _write(manifest_path, manifest)
    search = {
        "schema_version": 3,
        "research_role": PUBLIC_METHOD_ROLE,
        "iter_id": iter_id,
        "source_spec_path": None,
        "spec_hash": None,
        "candidate_manifest_path": manifest_path.relative_to(root).as_posix(),
        "candidate_manifest_sha256": _binding(root, manifest_path)["sha256"],
        "candidate_manifest_contract": "generic_candidate_family_v1",
        "data_feasibility_path": feasibility_path.relative_to(root).as_posix(),
        "paths": [{"name": "method", "candidate_count": 1}],
    }
    sources = []
    for index, kind in enumerate(("paper", "platform_docs")):
        sources.append(
            {
                "url": f"https://example.com/fixture-{index}",
                "source_type": kind,
                "published_or_updated_at": "2026-10-11",
                "credibility": "primary",
                "core_claim": "Synthetic metadata for a governance test.",
                "project_applicability": "Nonpromotable anonymous method.",
                "reflection": "No market evidence or executable strategy.",
                "source_kind": "official_author_implementation" if index else "primary_paper",
            }
        )
    cards_path = root / "reports/harness/source_cards/method-fixture.jsonl"
    cards_path.parent.mkdir(parents=True)
    cards = [
        {
            "claim_id": str(index),
            "iteration_id": iter_id,
            "claim": source["core_claim"],
            "source_url": source["url"],
            "source_type": source["source_type"],
            "accessed_at": "2026-10-11",
            "verification_status": "source_verified",
            "verified_at": "2026-10-11T00:00:00Z",
            "verification_method": "synthetic_governance_fixture",
        }
        for index, source in enumerate(sources)
    ]
    cards_path.write_text("\n".join(json.dumps(row) for row in cards) + "\n")
    source_bindings = [
        {
            "canonical_url": source["url"],
            "source_card_claim_id": str(index),
            "claim_fingerprint": claim_fingerprint(source["core_claim"]),
            "brief_claim_fingerprint": claim_fingerprint(source["core_claim"]),
        }
        for index, source in enumerate(sources)
    ]
    external = {
        "schema_version": 3,
        "research_role": PUBLIC_METHOD_ROLE,
        "iter_id": iter_id,
        "source_spec_path": None,
        "spec_hash": None,
        "sources": sources,
        "current_source_card_paths": [cards_path.relative_to(root).as_posix()],
        "source_evidence_bindings": source_bindings,
        "topic_coverage": ["definition", "input", "clock", "cost", "baseline", "limits"],
        "candidate_matrix_revisions": [{"method": "original"}],
    }
    _write(directory / "external-brief.json", external)
    _write(directory / "search-space.json", search)
    return directory, external, search, manifest, definition


def test_reviewed_method_uses_actual_definition_not_security_spec(tmp_path: Path) -> None:
    directory, external, search, _, _ = _fixture(tmp_path)
    assert public_method_role_applies(directory, tmp_path)
    assert _external_brief_blockers(external, public_method=True) == []
    assert (
        _candidate_manifest_blockers(
            directory / "candidate-manifest.json", search, tmp_path, expected_total=1
        )
        == []
    )
    ordinary = _external_brief_blockers(external)
    assert "external_brief_sources_lt_8:2" in ordinary
    assert "external_brief_paper_sources_lt_3:1" in ordinary


@pytest.mark.parametrize(
    "field",
    ["promotion_eligible", "paper_trading_allowed", "broker_activity_allowed", "real_market_claim"],
)
def test_method_cannot_acquire_trading_or_promotion_scope(tmp_path: Path, field: str) -> None:
    directory, external, search, manifest, definition = _fixture(tmp_path)
    definition[field] = True
    path = directory / "method-definition.json"
    _write(path, definition)
    manifest["candidates"][0]["method_definition_sha256"] = _binding(tmp_path, path)["sha256"]
    _write(directory / "candidate-manifest.json", manifest)
    search["candidate_manifest_sha256"] = _binding(tmp_path, directory / "candidate-manifest.json")[
        "sha256"
    ]
    blockers = _public_method_role_blockers(external, search, tmp_path)
    assert f"public_method_definition_{field}_must_be_false" in blockers


@pytest.mark.parametrize(
    "mutation",
    ["spec", "promotable", "mixed_role", "definition_hash", "review", "source", "canonical_copy"],
)
def test_method_exception_rejects_relabeling_and_binding_drift(
    tmp_path: Path, mutation: str
) -> None:
    directory, external, search, manifest, _ = _fixture(tmp_path)
    candidate = manifest["candidates"][0]
    if mutation == "spec":
        candidate["spec_path"] = "strategy_specs/real-strategy.yaml"
    elif mutation == "promotable":
        candidate["promotion_eligible"] = True
    elif mutation == "mixed_role":
        candidate["research_role"] = "strategy"
    elif mutation == "definition_hash":
        candidate["method_definition_sha256"] = "0" * 64
    elif mutation == "review":
        (directory / "independent-review.json").write_text('{"verdict":"revise_plan"}')
    elif mutation == "source":
        (directory / "official-implementation.py").write_text("changed")
    else:
        remote_manifest = directory / "preserved-program-manifest.json"
        _write(remote_manifest, manifest)
        search["candidate_manifest_path"] = remote_manifest.relative_to(tmp_path).as_posix()
        (directory / "candidate-manifest.json").write_text("{}")
    if mutation != "canonical_copy":
        _write(directory / "candidate-manifest.json", manifest)
        search["candidate_manifest_sha256"] = _binding(
            tmp_path, directory / "candidate-manifest.json"
        )["sha256"]
    assert _public_method_role_blockers(external, search, tmp_path)


def test_role_label_alone_does_not_change_applicability(tmp_path: Path) -> None:
    directory, external, search, _, _ = _fixture(tmp_path)
    search.pop("research_role")
    assert _public_method_role_blockers(external, search, tmp_path) == [
        "public_method_dossier_role_mismatch"
    ]
    _write(directory / "search-space.json", search)
    assert not public_method_role_applies(directory, tmp_path)


def test_method_reuses_knowledge_but_still_requires_scout(tmp_path: Path) -> None:
    directory, _, _, _, _ = _fixture(tmp_path)
    result = assess_iteration_knowledge(directory.name, tmp_path)
    assert result.payload["public_method_role_applicable"] is True
    assert "knowledge_sources_lt_8" not in result.payload["blocked"]
    assert "knowledge_scout_missing" in result.payload["blocked"]
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
    assert assess_iteration_knowledge(directory.name, tmp_path).payload["status"] == "ok"
    query.write_text("changed")
    with pytest.raises(ValueError, match="manifest hash mismatch"):
        assess_iteration_knowledge(directory.name, tmp_path)


def test_method_keeps_generic_contract_hash_checks(tmp_path: Path) -> None:
    directory, _, search, _, _ = _fixture(tmp_path)
    (directory / "costs.json").write_text("changed")
    blockers = _candidate_manifest_blockers(
        directory / "candidate-manifest.json", search, tmp_path, expected_total=1
    )
    assert "candidate_manifest_generic_costs_costs_sha256_mismatch" in blockers


@pytest.mark.parametrize(
    "claim", ["paper_ready_pass", "research_pass", "broker_activity_allowed", "real_market_claim"]
)
def test_final_method_publication_cannot_turn_into_market_qualification(
    tmp_path: Path, claim: str
) -> None:
    directory, _, _, _, _ = _fixture(tmp_path)
    evaluation_dir = directory / "evaluation-run"
    evaluation_dir.mkdir()
    decision = evaluation_dir / "decision-record.md"
    decision.write_text("- Decision: continue\n")
    ledger = evaluation_dir / "trial-ledger.jsonl"
    ledger.write_text('{"candidate_id":"M01"}\n')
    evaluation = evaluation_dir / "evaluation.json"
    receipt = {
        "schema_version": 1,
        "iter_id": directory.name,
        "evidence_publication_status": "complete",
        "decision": "continue",
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "promotion_eligible": False,
        "paper_trading_allowed": False,
        "broker_activity_allowed": False,
        "real_market_claim": False,
    }
    _write(evaluation, receipt)

    def publish() -> None:
        receipt["children"] = {
            name: {**_binding(tmp_path, path), "size_bytes": path.stat().st_size}
            for name, path in (
                ("decision_record", decision),
                ("trial_ledger", ledger),
                ("evaluation", evaluation),
            )
        }
        _write(evaluation_dir / "evaluation-receipt.json", receipt)

    publish()
    paths = iteration_dossier_paths(directory.name, tmp_path)
    assert _final_evaluation_receipt_blockers(paths, tmp_path)[0] == []
    receipt[claim] = True
    _write(evaluation, {key: value for key, value in receipt.items() if key != "children"})
    publish()
    blockers, _ = _final_evaluation_receipt_blockers(paths, tmp_path)
    assert f"public_method_final_receipt_{claim}_must_be_false" in blockers
    assert f"public_method_final_report_{claim}_must_be_false" in blockers
