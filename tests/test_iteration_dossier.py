from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
import yaml
from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.design_contract import (
    RESEARCH_DESIGN_BINDING_FIELDS,
    research_design_mapping,
)
from open_composer.research.iteration_dossier import (
    _campaign_contract_blockers,
    _campaign_universe_contract_blockers,
    _candidate_manifest_blockers,
    _data_feasibility_blockers,
    _final_evaluation_receipt_blockers,
    _generic_validation_contract_blockers,
    _q2_execution_map_blockers,
    _spec_iteration_binding_blockers,
    candidate_authorization_binding_sha256,
    init_iteration_dossier,
    iteration_dossier_paths,
    require_iteration_execution_gate,
    validate_iteration_dossier,
)
from open_composer.research.stock_momentum_q2_contract import (
    RUNNABLE_IDS,
    build_q2_execution_map,
)
from open_composer.strategy_versions import strategy_content_hash

EXPECTED_RESEARCH_DESIGN_BINDING_FIELDS = frozenset(
    {
        "campaign_contract_path",
        "candidate_manifest_path",
        "candidate_policy_contract_path",
        "cost_contract_path",
        "cumulative_trial_contract_path",
        "data_contract_path",
        "data_feasibility_path",
        "holdout_contract_path",
        "iter_id",
        "knowledge_contract",
        "preregistration_lock_path",
        "source_card_claim_ids",
        "source_cards_path",
        "universe_contract_path",
    }
)


def _research_binding_value(binding_field: str, variant: str = "primary") -> object:
    if binding_field == "knowledge_contract":
        return {"assessment_path": f"reports/research/knowledge/{variant}-assessment.json"}
    if binding_field == "source_card_claim_ids":
        return [f"claim-{variant}"]
    if binding_field == "iter_id":
        return f"missing_{variant}_iteration"
    return f"reports/research/contracts/{variant}-{binding_field}.json"


def test_iteration_dossier_init_writes_template_and_validate_blocks(
    sample_workspace: Path,
) -> None:
    paths = init_iteration_dossier("mom_minute_r1", sample_workspace)

    assert paths.external_brief_json.exists()
    assert paths.hypotheses_md.exists()
    assert paths.search_space_json.exists()
    assert paths.decision_record_md.exists()
    search = json.loads(paths.search_space_json.read_text(encoding="utf-8"))
    assert search["schema_version"] == 3
    assert search["created_at"].endswith("+00:00")

    result = validate_iteration_dossier("mom_minute_r1", sample_workspace)

    assert result.status == "blocked"
    assert "external_brief_sources_lt_8:0" in result.blocked
    assert "external_brief_paper_sources_lt_3:0" in result.blocked
    assert "search_space_paths_missing" in result.blocked
    assert "decision_record_still_template" in result.blocked


def test_generic_validation_contract_requires_directional_cscv(tmp_path: Path) -> None:
    path = tmp_path / "validation-contract.json"
    payload = {
        "family_gates": {"pbo_min_partitions": 20},
        "pbo": {
            "block_count": 8,
            "block_ids": [f"B{index:02d}" for index in range(1, 9)],
            "block_construction": {
                "algorithm": "split_ordered_common_sessions_into_contiguous_blocks",
                "remainder_allocation": "one_extra_session_to_earliest_block_ids_in_order",
                "maximum_size_difference": 1,
                "no_shuffle": True,
            },
            "in_sample_block_count": 4,
            "partition_enumeration": "all_directional_combinations",
            "evaluate_complementary_orientations": True,
            "expected_partition_count": 70,
            "minimum_valid_partition_count": 70,
            "selection_candidate_ids": ["A", "B", "C", "D", "E", "F"],
            "diagnostic_control_ids": ["X", "Y"],
            "valid_partition_requirements": [
                "all_selection_candidates_have_nonempty_finite_returns_on_both_sides",
                "all_candidate_Sharpe_values_are_defined",
                "exactly_four_in_sample_and_four_out_of_sample_blocks",
                "no_session_substitution_or_overlap",
                "deterministic_candidate_id_tie_break",
            ],
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert _generic_validation_contract_blockers(path) == []

    payload["pbo"]["partition_enumeration"] = "deduplicated_complementary_pairs"
    payload["pbo"]["evaluate_complementary_orientations"] = False
    payload["pbo"]["expected_partition_count"] = 35
    path.write_text(json.dumps(payload), encoding="utf-8")
    blockers = _generic_validation_contract_blockers(path)
    assert "candidate_manifest_generic_validation_pbo_partition_symmetry_invalid" in blockers
    assert "candidate_manifest_generic_validation_pbo_partition_count_invalid" in blockers


def test_campaign_candidate_authorization_hash_avoids_evidence_digest_cycle() -> None:
    candidate = {
        "candidate_id": "C01",
        "campaign_id": "campaign_gate_r1",
        "method": "deterministic_trend",
        "universe_contract_path": "reports/research/iterations/c01/universe-contract.json",
        "universe_contract_sha256": "a" * 64,
        "development_partition_contract_path": (
            "reports/research/iterations/c01/development-partition-contract.json"
        ),
        "development_partition_contract_sha256": "b" * 64,
    }
    original = candidate_authorization_binding_sha256(candidate)

    candidate["universe_contract_sha256"] = "c" * 64
    candidate["development_partition_contract_sha256"] = "d" * 64
    assert candidate_authorization_binding_sha256(candidate) == original

    candidate["method"] = "deterministic_reversal"
    assert candidate_authorization_binding_sha256(candidate) != original


def test_iteration_dossier_validate_passes_complete_dossier(sample_workspace: Path) -> None:
    paths = init_iteration_dossier("mom_minute_r1", sample_workspace)
    sources = [
        {
            "url": f"https://example.com/source-{idx}",
            "published_or_updated_at": "2026-01-01",
            "source_type": "paper" if idx < 3 else "platform_docs",
            "credibility": "high",
            "core_claim": f"claim {idx}",
            "project_applicability": "Defines a bounded minute momentum hypothesis.",
            "reflection": "May decay and is sensitive to transaction costs.",
        }
        for idx in range(8)
    ]
    paths.external_brief_json.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "iter_id": "mom_minute_r1",
                "strategy_name": "us_minute_momentum",
                "source_spec_path": None,
                "spec_hash": None,
                "objective": "US minute momentum round 1",
                "sources": sources,
                "topic_coverage": [
                    "intraday momentum",
                    "intraday reversal",
                    "cross-sectional momentum",
                    "overnight intraday decomposition",
                    "volatility-managed momentum",
                    "transaction costs",
                ],
                "candidate_matrix_revisions": [
                    {"path": "P1", "decision": "keep", "reason": "supported by sources"}
                ],
                "hypothesis_links": [{"hypothesis_id": "H1", "source_urls": [sources[0]["url"]]}],
            }
        ),
        encoding="utf-8",
    )
    paths.search_space_json.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "iter_id": "mom_minute_r1",
                "strategy_name": "us_minute_momentum",
                "source_spec_path": None,
                "spec_hash": None,
                "total_candidate_budget": 20,
                "paths": [
                    {
                        "name": "P1",
                        "candidate_count": 12,
                        "hypothesis_refs": ["H1"],
                        "parameters": {"lookback": [12, 24]},
                        "benchmark_family": ["QQQ", "BIL", "naive_momentum"],
                    },
                    {
                        "name": "P2",
                        "candidate_count": 8,
                        "hypothesis_refs": ["H2"],
                        "parameters": {"top_k": [1, 2]},
                        "benchmark_family": ["SPY", "BIL", "equal_weight_universe"],
                    },
                ],
                "trial_ledger_paths": [],
                "evaluation_report_paths": [],
                "cost_table_path": "reports/research/control/minute-momentum-feasibility.json",
                "data_feasibility_path": "reports/research/control/minute-momentum-feasibility.md",
            }
        ),
        encoding="utf-8",
    )
    paths.external_brief_md.write_text(_filled_md("External brief"), encoding="utf-8")
    paths.hypotheses_md.write_text(_hypotheses_md(), encoding="utf-8")
    paths.search_space_md.write_text(_filled_md("Search space"), encoding="utf-8")
    paths.decision_record_md.write_text(_decision_record_md("pending"), encoding="utf-8")

    result = validate_iteration_dossier("mom_minute_r1", sample_workspace)

    assert result.status == "ok"
    assert result.blocked == []


def test_iteration_dossier_requires_manifest_for_bound_campaign_before_backtest(
    sample_workspace: Path,
) -> None:
    paths = init_iteration_dossier("mom_minute_r1", sample_workspace)
    _write_complete_pre_backtest_payload(paths)
    campaign_path = (
        sample_workspace
        / "reports/research/campaigns/campaign_gate_r1/research-campaign-contract.json"
    )
    campaign_path.parent.mkdir(parents=True)
    campaign = _minimal_campaign_contract(child_iteration_ids=["mom_minute_r1"])
    campaign_path.write_text(json.dumps(campaign), encoding="utf-8")
    search = json.loads(paths.search_space_json.read_text(encoding="utf-8"))
    search["campaign_id"] = "campaign_gate_r1"
    search["campaign_contract_path"] = campaign_path.relative_to(sample_workspace).as_posix()
    search["campaign_contract_sha256"] = hashlib.sha256(campaign_path.read_bytes()).hexdigest()
    paths.search_space_json.write_text(json.dumps(search), encoding="utf-8")

    missing_manifest = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert "campaign_contract_child_candidate_manifest_missing" in missing_manifest.blocked

    campaign["child_iteration_ids"] = ["another_iteration"]
    campaign_path.write_text(json.dumps(campaign), encoding="utf-8")
    search["campaign_contract_sha256"] = hashlib.sha256(campaign_path.read_bytes()).hexdigest()
    paths.search_space_json.write_text(json.dumps(search), encoding="utf-8")
    blocked = validate_iteration_dossier("mom_minute_r1", sample_workspace)

    assert "campaign_contract_child_iteration_missing:mom_minute_r1" in blocked.blocked


@pytest.mark.parametrize(
    ("sha_field", "expected_blocker"),
    [
        (
            "universe_contract_sha256",
            "campaign_contract_candidate_evidence_sha256_mismatch:C01:universe_contract_sha256",
        ),
        (
            "development_partition_contract_sha256",
            "campaign_contract_candidate_evidence_sha256_mismatch:"
            "C01:development_partition_contract_sha256",
        ),
    ],
)
def test_campaign_candidate_evidence_sha256_binds_real_contract_files(
    sample_workspace: Path,
    sha_field: str,
    expected_blocker: str,
) -> None:
    campaign = _minimal_campaign_contract(child_iteration_ids=["mom_minute_r1"])
    campaign_path = (
        sample_workspace
        / "reports/research/campaigns/campaign_gate_r1/research-campaign-contract.json"
    )
    campaign_path.parent.mkdir(parents=True)
    campaign_path.write_text(json.dumps(campaign), encoding="utf-8")
    iteration_root = sample_workspace / "reports/research/iterations/mom_minute_r1"
    iteration_root.mkdir(parents=True)
    feasibility_path = iteration_root / "data-feasibility.json"
    feasibility_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "iter_id": "mom_minute_r1",
                "campaign_universe": {
                    "status": "ready",
                    "capability_ids": ["market.alpaca_bars"],
                },
            }
        ),
        encoding="utf-8",
    )
    universe_path = iteration_root / "universe-contract.json"
    universe_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "campaign_id": campaign["campaign_id"],
                "child_iteration_id": "mom_minute_r1",
                "hypothesis_id": "H1",
                "universe_selection": "fixed_long_lived",
                "promotion_eligible": True,
                "contract_status": "ready",
                "capability_ids": ["market.alpaca_bars"],
                "data_feasibility_binding": {
                    "path": feasibility_path.relative_to(sample_workspace).as_posix(),
                    "sha256": hashlib.sha256(feasibility_path.read_bytes()).hexdigest(),
                },
                "universe_definition": {
                    "membership_mode": "fixed_long_lived_symbols",
                    "symbols": ["SPY", "BIL"],
                    "selection_rule": "predeclared_long_lived_fixture_symbols",
                    "selection_frozen_at": "2026-08-15T17:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )
    partition_path = iteration_root / "development-partition-contract.json"
    partition_path.write_text(
        json.dumps({"partition_id": "development", "kind": "development"}),
        encoding="utf-8",
    )
    candidate_rows = [
        {
            "candidate_id": candidate["candidate_id"],
            "campaign_id": campaign["campaign_id"],
            "hypothesis_id": candidate["hypothesis_id"],
            "branch_id": candidate["branch_id"],
            "child_iteration_id": candidate["child_iteration_id"],
            "promotion_eligible": candidate["promotion_eligible"],
            "quality_metric": campaign["qd_archive"]["quality_metric"],
            "universe_contract_path": universe_path.relative_to(sample_workspace).as_posix(),
            "universe_contract_sha256": hashlib.sha256(universe_path.read_bytes()).hexdigest(),
            "development_partition_contract_path": (
                partition_path.relative_to(sample_workspace).as_posix()
            ),
            "development_partition_contract_sha256": hashlib.sha256(
                partition_path.read_bytes()
            ).hexdigest(),
        }
        for candidate in campaign["candidate_blueprints"]
    ]
    manifest_path = iteration_root / "candidate-manifest.json"
    manifest_path.write_text(json.dumps({"candidates": candidate_rows}), encoding="utf-8")
    search = {
        "iter_id": "mom_minute_r1",
        "campaign_id": campaign["campaign_id"],
        "campaign_contract_path": campaign_path.relative_to(sample_workspace).as_posix(),
        "campaign_contract_sha256": hashlib.sha256(campaign_path.read_bytes()).hexdigest(),
        "candidate_manifest_path": manifest_path.relative_to(sample_workspace).as_posix(),
        "data_feasibility_path": feasibility_path.relative_to(sample_workspace).as_posix(),
        "total_candidate_budget": len(candidate_rows),
    }

    assert (
        _campaign_contract_blockers(
            search,
            sample_workspace,
            stage="pre-discovery",
        )
        == []
    )

    candidate_rows[0][sha_field] = "a" * 64
    manifest_path.write_text(json.dumps({"candidates": candidate_rows}), encoding="utf-8")
    blocked = _campaign_contract_blockers(
        search,
        sample_workspace,
        stage="pre-discovery",
    )
    assert expected_blocker in blocked

    bound_path = universe_path if sha_field == "universe_contract_sha256" else partition_path
    candidate_rows[0][sha_field] = hashlib.sha256(bound_path.read_bytes()).hexdigest()
    universe_path.write_bytes(partition_path.read_bytes())
    candidate_rows[0]["universe_contract_sha256"] = hashlib.sha256(
        universe_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps({"candidates": candidate_rows}), encoding="utf-8")
    semantic_blocked = _campaign_contract_blockers(
        search,
        sample_workspace,
        stage="pre-discovery",
    )
    assert "campaign_contract_candidate_universe_contract:C01:schema_version_mismatch" in (
        semantic_blocked
    )


def test_new_and_registered_child_iterations_cannot_omit_campaign_binding(
    sample_workspace: Path,
) -> None:
    post_cutoff = {
        "schema_version": 3,
        "created_at": "2026-08-16T00:00:00Z",
        "iter_id": "brand_new_after_cutoff",
    }
    assert "campaign_contract_required_for_new_iteration" in _campaign_contract_blockers(
        post_cutoff,
        sample_workspace,
        stage="pre-discovery",
    )
    downgraded = {
        "schema_version": 1,
        "iter_id": "brand_new_after_cutoff",
    }
    downgraded_blockers = _campaign_contract_blockers(
        downgraded,
        sample_workspace,
        stage="pre-discovery",
    )
    assert "campaign_governance_schema_version_invalid_for_new_iteration" in downgraded_blockers
    assert "campaign_contract_required_for_new_iteration" in downgraded_blockers
    backdated = {
        "schema_version": 3,
        "created_at": "2026-08-14T00:00:00Z",
        "iter_id": "brand_new_after_cutoff",
    }
    assert "campaign_contract_required_for_new_iteration" in _campaign_contract_blockers(
        backdated,
        sample_workspace,
        stage="pre-discovery",
    )

    campaign = _minimal_campaign_contract(child_iteration_ids=["registered_child_r1"])
    campaign_path = (
        sample_workspace
        / "reports/research/campaigns/campaign_gate_r1/research-campaign-contract.json"
    )
    campaign_path.parent.mkdir(parents=True)
    campaign_path.write_text(json.dumps(campaign), encoding="utf-8")
    registered = {
        "schema_version": 1,
        "iter_id": "registered_child_r1",
    }
    blockers = _campaign_contract_blockers(
        registered,
        sample_workspace,
        stage="pre-discovery",
    )
    assert "campaign_contract_binding_missing_for_registered_child:campaign_gate_r1" in blockers


def test_registered_child_rejects_shadow_campaign_binding(sample_workspace: Path) -> None:
    campaign = _minimal_campaign_contract(child_iteration_ids=["registered_child_r1"])
    campaign_path = (
        sample_workspace
        / "reports/research/campaigns/campaign_gate_r1/research-campaign-contract.json"
    )
    campaign_path.parent.mkdir(parents=True)
    campaign_path.write_text(json.dumps(campaign), encoding="utf-8")

    shadow = deepcopy(campaign)
    shadow["campaign_id"] = "shadow_campaign_r1"
    shadow_path = sample_workspace / "reports/research/iterations/shadow-campaign.json"
    shadow_path.parent.mkdir(parents=True)
    shadow_path.write_text(json.dumps(shadow), encoding="utf-8")
    payload = {
        "schema_version": 3,
        "created_at": "2026-08-16T00:00:00Z",
        "iter_id": "registered_child_r1",
        "campaign_id": "shadow_campaign_r1",
        "campaign_contract_path": shadow_path.relative_to(sample_workspace).as_posix(),
        "campaign_contract_sha256": hashlib.sha256(shadow_path.read_bytes()).hexdigest(),
        "total_candidate_budget": 3,
    }

    blockers = _campaign_contract_blockers(
        payload,
        sample_workspace,
        stage="pre-discovery",
    )

    assert "campaign_contract_noncanonical_path" in blockers
    assert (
        "campaign_contract_registered_child_identity_mismatch:campaign_gate_r1:shadow_campaign_r1"
    ) in blockers


def test_pit_universe_requires_registered_capability_and_structured_membership(
    sample_workspace: Path,
) -> None:
    registry_path = sample_workspace / "capabilities/registry.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    alpaca = next(item for item in registry["capabilities"] if item["id"] == "market.alpaca_bars")
    alpaca["use_for"] = [*alpaca["use_for"], "point_in_time_universe"]
    registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")

    iteration_root = sample_workspace / "reports/research/iterations/mom_breadth_pit_xsmom_r1"
    iteration_root.mkdir(parents=True)
    feasibility_path = iteration_root / "data-feasibility.json"
    feasibility = {
        "schema_version": 1,
        "iter_id": "mom_breadth_pit_xsmom_r1",
        "campaign_universe": {
            "status": "ready",
            "capability_ids": ["market.alpaca_bars"],
        },
    }
    feasibility_path.write_text(json.dumps(feasibility), encoding="utf-8")
    membership_path = iteration_root / "pit-membership.json"
    membership = {
        "schema_version": 1,
        "source": "licensed_pit_security_master",
        "fetched_at": "2026-08-15T12:00:00Z",
        "memberships": [
            {
                "security_id": "sec-001",
                "valid_from": "2020-01-01",
                "valid_to": None,
                "delisting_return": None,
                "liquidity_visible_at": "2019-12-31T21:00:00Z",
            }
        ],
    }
    membership_path.write_text(json.dumps(membership), encoding="utf-8")
    universe_path = iteration_root / "universe-contract.json"
    universe = {
        "schema_version": 1,
        "campaign_id": "mom_breadth_qd_r1",
        "child_iteration_id": "mom_breadth_pit_xsmom_r1",
        "hypothesis_id": "H1_PIT_XSMOM",
        "universe_selection": "point_in_time",
        "promotion_eligible": True,
        "contract_status": "ready",
        "capability_ids": ["market.alpaca_bars"],
        "data_feasibility_binding": {
            "path": feasibility_path.relative_to(sample_workspace).as_posix(),
            "sha256": hashlib.sha256(feasibility_path.read_bytes()).hexdigest(),
        },
        "universe_definition": {
            "membership_mode": "point_in_time_membership",
            "membership_artifact_path": membership_path.relative_to(sample_workspace).as_posix(),
            "membership_artifact_sha256": hashlib.sha256(membership_path.read_bytes()).hexdigest(),
            "permanent_security_id_field": "security_id",
            "membership_valid_from_field": "valid_from",
            "membership_valid_to_field": "valid_to",
            "delisting_return_field": "delisting_return",
            "corporate_action_policy": (
                "point_in_time_split_dividend_adjusted_with_delisting_returns"
            ),
            "liquidity_visible_at_field": "liquidity_visible_at",
        },
    }
    universe_path.write_text(json.dumps(universe), encoding="utf-8")
    candidate = SimpleNamespace(
        child_iteration_id="mom_breadth_pit_xsmom_r1",
        hypothesis_id="H1_PIT_XSMOM",
        promotion_eligible=True,
    )
    hypothesis = SimpleNamespace(universe_selection="point_in_time")

    assert (
        _campaign_universe_contract_blockers(
            universe_path,
            candidate_id="PIT01",
            root=sample_workspace,
            expected_campaign_id="mom_breadth_qd_r1",
            expected_candidate=candidate,
            expected_hypothesis=hypothesis,
            expected_data_feasibility_path=(
                feasibility_path.relative_to(sample_workspace).as_posix()
            ),
        )
        == []
    )

    universe["capability_ids"] = ["not.registered.pit_capability"]
    feasibility["campaign_universe"]["capability_ids"] = ["not.registered.pit_capability"]
    feasibility_path.write_text(json.dumps(feasibility), encoding="utf-8")
    universe["data_feasibility_binding"]["sha256"] = hashlib.sha256(
        feasibility_path.read_bytes()
    ).hexdigest()
    membership_path.write_text("this is not a membership table", encoding="utf-8")
    universe["universe_definition"]["membership_artifact_sha256"] = hashlib.sha256(
        membership_path.read_bytes()
    ).hexdigest()
    universe_path.write_text(json.dumps(universe), encoding="utf-8")

    blockers = _campaign_universe_contract_blockers(
        universe_path,
        candidate_id="PIT01",
        root=sample_workspace,
        expected_campaign_id="mom_breadth_qd_r1",
        expected_candidate=candidate,
        expected_hypothesis=hypothesis,
        expected_data_feasibility_path=feasibility_path.relative_to(sample_workspace).as_posix(),
    )
    assert (
        "campaign_contract_candidate_universe_contract:PIT01:"
        "capability_ids_unregistered:not.registered.pit_capability"
    ) in blockers
    assert (
        "campaign_contract_candidate_universe_contract:PIT01:point_in_time_membership_invalid_json"
    ) in blockers

    feasibility_path.write_text("{}", encoding="utf-8")
    universe["data_feasibility_binding"]["sha256"] = hashlib.sha256(
        feasibility_path.read_bytes()
    ).hexdigest()
    universe_path.write_text(json.dumps(universe), encoding="utf-8")
    feasibility_blockers = _campaign_universe_contract_blockers(
        universe_path,
        candidate_id="PIT01",
        root=sample_workspace,
        expected_campaign_id="mom_breadth_qd_r1",
        expected_candidate=candidate,
        expected_hypothesis=hypothesis,
        expected_data_feasibility_path=feasibility_path.relative_to(sample_workspace).as_posix(),
    )
    assert (
        "campaign_contract_candidate_universe_contract:PIT01:"
        "data_feasibility_schema_version_mismatch"
    ) in feasibility_blockers


def test_iteration_dossier_rejects_child_candidate_budget_above_campaign_allocation(
    sample_workspace: Path,
) -> None:
    paths = init_iteration_dossier("mom_minute_r1", sample_workspace)
    _write_complete_pre_backtest_payload(paths)
    campaign_path = (
        sample_workspace
        / "reports/research/campaigns/campaign_gate_r1/research-campaign-contract.json"
    )
    campaign_path.parent.mkdir(parents=True)
    campaign = _minimal_campaign_contract(child_iteration_ids=["mom_minute_r1"])
    campaign["candidate_blueprints"] = campaign["candidate_blueprints"][:2]
    campaign["branch_quotas"][0].update({"min_candidates": 2, "max_candidates": 2})
    campaign["exposure_budgets"] = {
        "candidate_budget": 2,
        "cumulative_trial_exposure_budget": 2,
    }
    campaign_path.write_text(json.dumps(campaign), encoding="utf-8")
    search = json.loads(paths.search_space_json.read_text(encoding="utf-8"))
    search["campaign_id"] = "campaign_gate_r1"
    search["campaign_contract_path"] = campaign_path.relative_to(sample_workspace).as_posix()
    search["campaign_contract_sha256"] = hashlib.sha256(campaign_path.read_bytes()).hexdigest()
    paths.search_space_json.write_text(json.dumps(search), encoding="utf-8")

    result = validate_iteration_dossier("mom_minute_r1", sample_workspace)

    assert "campaign_contract_child_candidate_budget_mismatch:mom_minute_r1:12:2" in result.blocked


def test_iteration_dossier_blocks_payload_iter_id_mismatch(sample_workspace: Path) -> None:
    paths = init_iteration_dossier("mom_minute_r1", sample_workspace)
    payload = json.loads(paths.external_brief_json.read_text(encoding="utf-8"))
    payload["iter_id"] = "other_round"
    paths.external_brief_json.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_iteration_dossier("mom_minute_r1", sample_workspace)

    assert "iteration_payload_iter_id_mismatch" in result.blocked


def test_iteration_dossier_final_stage_requires_artifact_refs(sample_workspace: Path) -> None:
    paths = init_iteration_dossier("mom_minute_r1", sample_workspace)
    _write_complete_pre_backtest_payload(paths)
    paths.decision_record_md.write_text(_decision_record_md("continue"), encoding="utf-8")

    result = validate_iteration_dossier("mom_minute_r1", sample_workspace, stage="final")

    assert "search_space_trial_ledger_paths_empty_final" in result.blocked
    assert "search_space_evaluation_report_paths_empty_final" in result.blocked


def test_final_stage_uses_complete_receipt_bound_evaluation_decision(
    sample_workspace: Path,
) -> None:
    paths = init_iteration_dossier("mom_minute_r1", sample_workspace)
    _write_complete_pre_backtest_payload(paths)
    paths.decision_record_md.write_text(_decision_record_md("pending"), encoding="utf-8")
    evaluation_dir = paths.root / "evaluation-run"
    evaluation_dir.mkdir()
    decision_path = evaluation_dir / "decision-record.md"
    evaluation_path = evaluation_dir / "evaluation-report.json"
    trial_path = evaluation_dir / "trial-ledger.jsonl"
    decision_path.write_text(_decision_record_md("stop"), encoding="utf-8")
    evaluation = {
        "decision": "stop",
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
    }
    evaluation_path.write_text(json.dumps(evaluation), encoding="utf-8")
    trial_path.write_text('{"candidate_id":"P1"}\n', encoding="utf-8")

    search = json.loads(paths.search_space_json.read_text(encoding="utf-8"))
    search["trial_ledger_paths"] = [str(trial_path.relative_to(sample_workspace))]
    search["evaluation_report_paths"] = [str(evaluation_path.relative_to(sample_workspace))]
    paths.search_space_json.write_text(json.dumps(search), encoding="utf-8")

    def binding(path: Path) -> dict[str, object]:
        return {
            "path": str(path.relative_to(sample_workspace)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size_bytes": path.stat().st_size,
        }

    receipt = {
        "schema_version": 1,
        "iter_id": "mom_minute_r1",
        "evidence_publication_status": "complete",
        **evaluation,
        "children": {
            "decision_record": binding(decision_path),
            "evaluation": binding(evaluation_path),
            "trial_ledger": binding(trial_path),
        },
    }
    (evaluation_dir / "evaluation-receipt.json").write_text(json.dumps(receipt), encoding="utf-8")

    result = validate_iteration_dossier("mom_minute_r1", sample_workspace, stage="final")

    assert "decision_record_missing_continue_pivot_stop" not in result.blocked
    assert not any(item.startswith("final_evaluation_") for item in result.blocked)

    decision_path.write_text(_decision_record_md("continue"), encoding="utf-8")
    tampered = validate_iteration_dossier("mom_minute_r1", sample_workspace, stage="final")
    assert "final_evaluation_child_decision_record_sha256_mismatch" in tampered.blocked


def test_generic_final_receipt_requires_canonical_decision_path_and_exact_value(
    tmp_path: Path,
) -> None:
    paths = iteration_dossier_paths("mom_minute_r1", tmp_path)
    evaluation_dir = paths.root / "evaluation-run"
    evaluation_dir.mkdir(parents=True)
    canonical_decision = evaluation_dir / "decision-record.md"
    alternate_decision = evaluation_dir / "alternate-decision.md"
    evaluation_path = evaluation_dir / "evaluation-report.json"
    trial_path = evaluation_dir / "trial-ledger.jsonl"
    canonical_decision.write_text(_decision_record_md("continue"), encoding="utf-8")
    alternate_decision.write_text(_decision_record_md("continue"), encoding="utf-8")
    evaluation = {
        "decision": "continue",
        "workflow_pass": True,
        "research_pass": True,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
    }
    evaluation_path.write_text(json.dumps(evaluation), encoding="utf-8")
    trial_path.write_text('{"candidate_id":"P1"}\n', encoding="utf-8")
    receipt = {
        "schema_version": 1,
        "iter_id": "mom_minute_r1",
        "evidence_publication_status": "complete",
        **evaluation,
        "children": {
            "decision_record": _test_binding(alternate_decision, tmp_path),
            "evaluation": _test_binding(evaluation_path, tmp_path),
            "trial_ledger": _test_binding(trial_path, tmp_path),
        },
    }
    receipt_path = evaluation_dir / "evaluation-receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    noncanonical, authoritative = _final_evaluation_receipt_blockers(paths, tmp_path)

    assert "final_evaluation_child_decision_record_path_mismatch" in noncanonical
    assert authoritative is None

    receipt["decision"] = "continue_arbitrary_suffix"
    evaluation["decision"] = receipt["decision"]
    evaluation_path.write_text(json.dumps(evaluation), encoding="utf-8")
    receipt["children"]["decision_record"] = _test_binding(canonical_decision, tmp_path)
    receipt["children"]["evaluation"] = _test_binding(evaluation_path, tmp_path)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    prefixed, _ = _final_evaluation_receipt_blockers(paths, tmp_path)

    assert "final_evaluation_receipt_decision_invalid" in prefixed


def test_r4_v2_final_receipt_accepts_exact_complete_publication(tmp_path: Path) -> None:
    paths, _, _, child_paths, _ = _write_r4_final_receipt_fixture(tmp_path)

    blockers, authoritative = _final_evaluation_receipt_blockers(paths, tmp_path)

    assert blockers == []
    assert authoritative == child_paths["decision_record"]


def test_r5_v3_final_receipt_accepts_exact_complete_publication(tmp_path: Path) -> None:
    paths, _, _, child_paths, _ = _write_r5_final_receipt_fixture(tmp_path)

    blockers, authoritative = _final_evaluation_receipt_blockers(paths, tmp_path)

    assert blockers == []
    assert authoritative == child_paths["decision_record"]


def test_r5_v3_final_receipt_rejects_tampered_external_harness_binding(
    tmp_path: Path,
) -> None:
    paths, _, _, _, _ = _write_r5_final_receipt_fixture(tmp_path)
    verify_path = tmp_path / "reports/harness/verify/us_multiasset_forward_mm_r5_c01.json"
    verify_path.write_text('{"tampered":true}\n', encoding="utf-8")

    blockers, _ = _final_evaluation_receipt_blockers(paths, tmp_path)

    assert "final_evaluation_harness_R5C01_verify_receipt_sha256_mismatch" in blockers


def test_r5_v3_final_receipt_accepts_complete_staged_publication(tmp_path: Path) -> None:
    paths, _, _, _, _ = _write_r5_final_receipt_fixture(tmp_path)
    staged = paths.root / ".r5-evaluation-stage-test"
    (paths.root / "evaluation-run").rename(staged)

    blockers, authoritative = _final_evaluation_receipt_blockers(
        paths,
        tmp_path,
        staged_evaluation_dir=staged,
    )

    assert blockers == []
    assert authoritative == staged / "decision-record.md"


def test_r5_finalize_recovers_sealed_publication_without_price_recomputation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from open_composer.research import multiasset_forward_multimodal_r5 as r5_module

    paths, _, _, _, _ = _write_r5_final_receipt_fixture(tmp_path)
    evaluation_dir = paths.root / "evaluation-run"
    evaluation = json.loads((evaluation_dir / "evaluation-report.json").read_text(encoding="utf-8"))
    attempt_hash = evaluation["preflight"]["evaluation_attempt"]["sha256"]
    staged = paths.root / f".r5-evaluation-stage-{attempt_hash[:16]}"
    evaluation_dir.rename(staged)
    r5_module._seal_evidence_directory(staged)

    custody_receipt = tmp_path / "external-custody-receipt.json"
    custody_receipt.write_text("{}\n", encoding="utf-8")
    custody_receipt.chmod(0o400)
    custody = SimpleNamespace(
        receipt_path=custody_receipt,
        receipt_sha256="c" * 64,
    )
    staged_verifications: list[bool] = []
    monkeypatch.setattr(r5_module, "_verify_recovery_lock_identity", lambda *args, **kwargs: None)
    monkeypatch.setattr(r5_module, "_reverify_locked_inputs", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        r5_module,
        "_verify_staged_publication",
        lambda *args, **kwargs: staged_verifications.append(True),
    )
    monkeypatch.setattr(
        r5_module,
        "_write_r5_evaluation_custody",
        lambda *args, **kwargs: custody,
    )
    monkeypatch.setattr(
        r5_module,
        "validate_iteration_dossier",
        lambda *args, **kwargs: SimpleNamespace(ok=True, blocked=[]),
    )
    monkeypatch.setattr(
        r5_module,
        "load_r5_panel",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("price path called")),
    )
    monkeypatch.setattr(
        r5_module,
        "build_point_in_time_features",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("feature path called")),
    )

    result = r5_module.finalize_multiasset_forward_multimodal_r5(
        tmp_path,
        expected_lock_anchor_sha256="a" * 64,
        custody_dir=(tmp_path.parent / "custody").resolve(),
    )

    assert result.evaluation_path == paths.root / "evaluation-run/evaluation-report.json"
    assert result.custody_receipt_sha256 == "c" * 64
    assert staged_verifications == [True]
    assert not staged.exists()


def test_r5_v3_final_receipt_requires_read_only_evaluation_anchor(tmp_path: Path) -> None:
    missing_root = tmp_path / "missing"
    paths, _, _, _, _ = _write_r5_final_receipt_fixture(missing_root)
    anchor_path = paths.root / "evaluation-run/evaluation-anchor.json"
    anchor_path.chmod(0o600)
    anchor_path.unlink()

    missing, _ = _final_evaluation_receipt_blockers(paths, missing_root)

    assert "final_evaluation_anchor_missing" in missing

    writable_root = tmp_path / "writable"
    paths, _, _, _, _ = _write_r5_final_receipt_fixture(writable_root)
    anchor_path = paths.root / "evaluation-run/evaluation-anchor.json"
    anchor_path.chmod(0o600)

    writable, _ = _final_evaluation_receipt_blockers(paths, writable_root)

    assert "final_evaluation_anchor_not_read_only" in writable


def test_r5_v3_evaluation_anchor_rejects_postpublication_receipt_rewrite(
    tmp_path: Path,
) -> None:
    paths, receipt_path, receipt, _, _ = _write_r5_final_receipt_fixture(tmp_path)
    receipt["evidence_publication_status"] = "rewritten"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    blockers, _ = _final_evaluation_receipt_blockers(paths, tmp_path)

    assert "final_evaluation_receipt_incomplete" in blockers
    assert "final_evaluation_anchor_semantics_invalid" in blockers
    assert "final_evaluation_anchor_receipt_binding_mismatch" in blockers


def test_r5_v3_final_receipt_requires_lock_custody_bindings(tmp_path: Path) -> None:
    paths, _, _, _, _ = _write_r5_final_receipt_fixture(tmp_path)
    attempt_path = paths.root / "evaluation-attempt.json"
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    del attempt["lock_custody_receipt_sha256"]
    attempt_path.write_text(json.dumps(attempt), encoding="utf-8")

    blockers, _ = _final_evaluation_receipt_blockers(paths, tmp_path)

    assert "final_evaluation_attempt_custody_binding_invalid" in blockers
    assert "final_evaluation_preflight_attempt_custody_mismatch" in blockers


def test_r5_v3_final_receipt_rejects_unbound_and_nonregular_inventory(
    tmp_path: Path,
) -> None:
    paths, _, _, _, _ = _write_r5_final_receipt_fixture(tmp_path)
    evaluation_dir = paths.root / "evaluation-run"
    (evaluation_dir / "unbound-directory").mkdir()
    (evaluation_dir / "broken-link").symlink_to("missing-target")

    blockers, _ = _final_evaluation_receipt_blockers(paths, tmp_path)

    extras = next(
        item for item in blockers if item.startswith("final_evaluation_run_inventory_extra:")
    )
    assert "broken-link" in extras
    assert "unbound-directory" in extras
    assert "final_evaluation_run_inventory_non_regular" in blockers


def test_r5_v3_final_receipt_rejects_semantically_invalid_attempt_and_checks(
    tmp_path: Path,
) -> None:
    paths, receipt_path, receipt, _, _ = _write_r5_final_receipt_fixture(tmp_path)
    attempt_path = paths.root / "evaluation-attempt.json"
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    attempt["status"] = "reserved"
    attempt_path.write_text(json.dumps(attempt), encoding="utf-8")
    receipt["prepublication_checks"]["staged_ledger_verification_pass"] = False
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    blockers, _ = _final_evaluation_receipt_blockers(paths, tmp_path)

    assert "final_evaluation_attempt_semantics_invalid" in blockers
    assert "final_evaluation_prepublication_checks_mismatch" in blockers


def test_r5_v3_final_receipt_rejects_failed_staged_ledger_verification(
    tmp_path: Path,
) -> None:
    paths, receipt_path, receipt, child_paths, _ = _write_r5_final_receipt_fixture(tmp_path)
    evaluation = json.loads(child_paths["evaluation"].read_text(encoding="utf-8"))
    evaluation["evidence_reconciliation"]["staged_ledger_verification"]["pass"] = False
    child_paths["evaluation"].write_text(json.dumps(evaluation), encoding="utf-8")
    receipt["children"]["evaluation"] = _test_binding(child_paths["evaluation"], tmp_path)
    receipt["prepublication_checks"]["staged_ledger_verification_pass"] = False
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    blockers, _ = _final_evaluation_receipt_blockers(paths, tmp_path)

    assert "final_evaluation_staged_ledger_verification_not_passed" in blockers


def test_r5_v3_final_receipt_rejects_wrong_contract_report_and_decision(
    tmp_path: Path,
) -> None:
    paths, receipt_path, receipt, child_paths, _ = _write_r5_final_receipt_fixture(tmp_path)
    receipt["receipt_contract"] = "multiasset_forward_multimodal_r4_v3"
    receipt["decision"] = "stop_r4"
    evaluation = json.loads(child_paths["evaluation"].read_text(encoding="utf-8"))
    evaluation["decision"] = "stop_r4"
    evaluation["report_type"] = "multiasset_forward_multimodal_r4_matched_transfer_evaluation"
    child_paths["evaluation"].write_text(json.dumps(evaluation), encoding="utf-8")
    receipt["children"]["evaluation"] = _test_binding(child_paths["evaluation"], tmp_path)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    blockers, _ = _final_evaluation_receipt_blockers(paths, tmp_path)

    assert "final_evaluation_receipt_contract_mismatch" in blockers
    assert "final_evaluation_receipt_decision_invalid" in blockers
    assert "final_evaluation_receipt_decision_status_mismatch" in blockers
    assert "final_evaluation_report_type_mismatch" in blockers


def test_r4_v2_final_receipt_rejects_omitted_extra_and_aliased_children(
    tmp_path: Path,
) -> None:
    omitted_root = tmp_path / "omitted"
    paths, receipt_path, receipt, _, _ = _write_r4_final_receipt_fixture(omitted_root)
    del receipt["children"]["feature_ledger"]
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    omitted, _ = _final_evaluation_receipt_blockers(paths, omitted_root)

    assert "final_evaluation_child_feature_ledger_missing" in omitted

    extra_root = tmp_path / "extra"
    paths, receipt_path, receipt, _, _ = _write_r4_final_receipt_fixture(extra_root)
    extra_path = paths.root / "evaluation-run" / "extra.json"
    extra_path.write_text("{}\n", encoding="utf-8")
    receipt["children"]["extra"] = _test_binding(extra_path, extra_root)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    extra, _ = _final_evaluation_receipt_blockers(paths, extra_root)

    assert "final_evaluation_receipt_unexpected_children:extra" in extra

    aliased_root = tmp_path / "aliased"
    paths, receipt_path, receipt, _, _ = _write_r4_final_receipt_fixture(aliased_root)
    receipt["children"]["prediction_ledger"] = deepcopy(receipt["children"]["feature_ledger"])
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    aliased, _ = _final_evaluation_receipt_blockers(paths, aliased_root)

    assert "final_evaluation_receipt_child_paths_not_unique" in aliased
    assert "final_evaluation_child_prediction_ledger_path_mismatch" in aliased


def test_r4_v2_final_receipt_rejects_malformed_boolean_status(tmp_path: Path) -> None:
    paths, receipt_path, receipt, child_paths, _ = _write_r4_final_receipt_fixture(tmp_path)
    evaluation = json.loads(child_paths["evaluation"].read_text(encoding="utf-8"))
    receipt["research_pass"] = "false"
    evaluation["research_pass"] = "false"
    child_paths["evaluation"].write_text(json.dumps(evaluation), encoding="utf-8")
    receipt["children"]["evaluation"] = _test_binding(child_paths["evaluation"], tmp_path)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    blockers, _ = _final_evaluation_receipt_blockers(paths, tmp_path)

    assert "final_evaluation_receipt_research_pass_not_boolean" in blockers
    assert "final_evaluation_report_research_pass_not_boolean" in blockers


def test_r4_v2_final_receipt_rejects_wrong_lock_hash_and_size(tmp_path: Path) -> None:
    hash_root = tmp_path / "hash"
    paths, _, _, _, lock_paths = _write_r4_final_receipt_fixture(hash_root)
    lock_paths["runner_lock"].write_text('{"tampered":true}\n', encoding="utf-8")

    wrong_hash, _ = _final_evaluation_receipt_blockers(paths, hash_root)

    assert "final_evaluation_runner_lock_sha256_mismatch" in wrong_hash

    size_root = tmp_path / "size"
    paths, receipt_path, receipt, _, _ = _write_r4_final_receipt_fixture(size_root)
    receipt["preregistration_lock"]["size_bytes"] += 1
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    wrong_size, _ = _final_evaluation_receipt_blockers(paths, size_root)

    assert "final_evaluation_preregistration_lock_size_mismatch" in wrong_size


def test_r4_v2_final_receipt_rejects_noncanonical_and_prefixed_decisions(
    tmp_path: Path,
) -> None:
    path_root = tmp_path / "path"
    paths, receipt_path, receipt, _, _ = _write_r4_final_receipt_fixture(path_root)
    alternate = paths.root / "evaluation-run" / "alternate-decision.md"
    alternate.write_text(_decision_record_md("stop"), encoding="utf-8")
    receipt["children"]["decision_record"] = _test_binding(alternate, path_root)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    noncanonical, authoritative = _final_evaluation_receipt_blockers(paths, path_root)

    assert "final_evaluation_child_decision_record_path_mismatch" in noncanonical
    assert authoritative is None

    prefix_root = tmp_path / "prefix"
    paths, receipt_path, receipt, child_paths, _ = _write_r4_final_receipt_fixture(prefix_root)
    receipt["decision"] = "continue_arbitrary_suffix"
    receipt["research_pass"] = True
    child_paths["decision_record"].write_text(_decision_record_md("continue"), encoding="utf-8")
    evaluation = json.loads(child_paths["evaluation"].read_text(encoding="utf-8"))
    evaluation["decision"] = receipt["decision"]
    evaluation["research_pass"] = True
    child_paths["evaluation"].write_text(json.dumps(evaluation), encoding="utf-8")
    receipt["children"]["decision_record"] = _test_binding(
        child_paths["decision_record"], prefix_root
    )
    receipt["children"]["evaluation"] = _test_binding(child_paths["evaluation"], prefix_root)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    prefixed, _ = _final_evaluation_receipt_blockers(paths, prefix_root)

    assert "final_evaluation_receipt_decision_invalid" in prefixed
    assert "final_evaluation_receipt_decision_status_mismatch" in prefixed


def test_q2_stages_lazy_validate_outputs_and_require_final_artifacts(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    iter_id = "mom_stock_intraday_codesign_q1"
    paths = init_iteration_dossier(iter_id, sample_workspace)
    paths.search_space_json.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "iter_id": iter_id,
                "strategy_name": "us_stock_momentum_codesign_daily_q1",
                "source_spec_path": None,
                "spec_hash": None,
                "total_candidate_budget": 1,
                "paths": [
                    {
                        "name": "deterministic_daily",
                        "candidate_count": 1,
                        "hypothesis_refs": ["Q-H1"],
                        "parameters": {"method": ["mom_12_1"]},
                        "benchmark_family": ["SPY"],
                    }
                ],
                "trial_ledger_paths": [],
                "evaluation_report_paths": [],
                "cost_table_path": "",
                "data_feasibility_path": "",
            }
        ),
        encoding="utf-8",
    )
    paths.decision_record_md.write_text(
        """# Decision Record

## Q.2

- Path: historical current-universe diagnostics.
- Decision: pending.
- Reason: The diagnostic ledger remains incomplete and cannot establish a qualified result.
- Next iteration suggestion: Record complete accounting before considering any later work.
""",
        encoding="utf-8",
    )

    calls: list[Path] = []
    future_module = ModuleType("open_composer.research.stock_momentum_codesign_q2")

    def validate_q2_output_artifacts(root: Path) -> list[str]:
        calls.append(root)
        return ["q2_future_output_blocker"]

    future_module.validate_q2_output_artifacts = validate_q2_output_artifacts
    monkeypatch.setitem(
        sys.modules,
        "open_composer.research.stock_momentum_codesign_q2",
        future_module,
    )

    preflight = validate_iteration_dossier(iter_id, sample_workspace, stage="q2-preflight")
    assert calls == []
    assert "q2_future_output_blocker" not in preflight.blocked
    assert "search_space_trial_ledger_paths_empty_final" not in preflight.blocked
    assert "decision_record_missing_continue_pivot_stop" not in preflight.blocked

    final = validate_iteration_dossier(iter_id, sample_workspace, stage="final")
    assert calls == [sample_workspace]
    assert "q2_future_output_blocker" in final.blocked
    assert "search_space_trial_ledger_paths_empty_final" in final.blocked
    assert "decision_record_missing_continue_pivot_stop" in final.blocked

    q2_final = validate_iteration_dossier(iter_id, sample_workspace, stage="q2-final")
    assert calls == [sample_workspace, sample_workspace]
    assert "q2_future_output_blocker" in q2_final.blocked
    assert "search_space_trial_ledger_paths_empty_final" in q2_final.blocked
    assert "decision_record_missing_continue_pivot_stop" in q2_final.blocked


def test_iteration_dossier_enforces_declared_knowledge_contract(
    sample_workspace: Path,
) -> None:
    paths = init_iteration_dossier("mom_minute_r1", sample_workspace)
    _write_complete_pre_backtest_payload(paths)
    search = json.loads(paths.search_space_json.read_text(encoding="utf-8"))
    artifact_root = paths.root
    artifacts = {
        "assessment_path": artifact_root / "knowledge-assessment.json",
        "scout_path": artifact_root / "knowledge-scout.json",
        "model_reuse_decision_path": artifact_root / "model-reuse-decision.json",
        "modality_role_matrix_path": artifact_root / "modality-role-matrix.json",
    }
    for field_name, path in artifacts.items():
        payload = (
            {
                "status": "ok",
                "external_brief_path": paths.external_brief_json.relative_to(
                    sample_workspace
                ).as_posix(),
                "external_brief_sha256": hashlib.sha256(
                    paths.external_brief_json.read_bytes()
                ).hexdigest(),
            }
            if field_name == "assessment_path"
            else {"rows": []}
        )
        path.write_text(json.dumps(payload), encoding="utf-8")
    search["knowledge_contract"] = {
        **{
            field_name: path.relative_to(sample_workspace).as_posix()
            for field_name, path in artifacts.items()
        },
        "required_visibility_partitions": [
            "public_literature",
            "train_only_empirical",
            "challenge_result",
            "forward_observation",
        ],
    }
    paths.search_space_json.write_text(json.dumps(search), encoding="utf-8")

    passed = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert passed.status == "ok"

    brief = json.loads(paths.external_brief_json.read_text(encoding="utf-8"))
    brief["objective"] = "changed after knowledge assessment"
    paths.external_brief_json.write_text(json.dumps(brief), encoding="utf-8")
    stale = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert "knowledge_contract_external_brief_sha256_mismatch" in stale.blocked
    brief["objective"] = "US minute momentum round 1"
    paths.external_brief_json.write_text(json.dumps(brief), encoding="utf-8")

    artifacts["scout_path"].unlink()
    blocked = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert "knowledge_contract_missing_artifact_scout_path" in blocked.blocked


def test_iteration_dossier_blocks_non_ok_knowledge_assessment(
    sample_workspace: Path,
) -> None:
    paths = init_iteration_dossier("mom_minute_r1", sample_workspace)
    _write_complete_pre_backtest_payload(paths)
    search = json.loads(paths.search_space_json.read_text(encoding="utf-8"))
    fields = {}
    for name in [
        "assessment_path",
        "scout_path",
        "model_reuse_decision_path",
        "modality_role_matrix_path",
    ]:
        path = paths.root / f"{name}.json"
        path.write_text(
            json.dumps({"status": "blocked"} if name == "assessment_path" else {}),
            encoding="utf-8",
        )
        fields[name] = path.relative_to(sample_workspace).as_posix()
    search["knowledge_contract"] = {
        **fields,
        "required_visibility_partitions": [
            "public_literature",
            "train_only_empirical",
            "challenge_result",
            "forward_observation",
        ],
    }
    paths.search_space_json.write_text(json.dumps(search), encoding="utf-8")

    result = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert "knowledge_contract_assessment_not_ok" in result.blocked


def test_iteration_dossier_validates_machine_candidate_manifest(
    sample_workspace: Path,
) -> None:
    paths = init_iteration_dossier("mom_minute_r1", sample_workspace)
    _write_complete_pre_backtest_payload(paths)
    search = json.loads(paths.search_space_json.read_text(encoding="utf-8"))
    search["total_candidate_budget"] = 1
    search["paths"][0]["candidate_count"] = 1
    search["data_feasibility_path"] = "reports/research/control/mom-minute-data-feasibility.json"
    manifest_path = paths.root / "candidate-manifest.json"
    search["candidate_manifest_path"] = manifest_path.relative_to(sample_workspace).as_posix()
    paths.search_space_json.write_text(json.dumps(search), encoding="utf-8")
    spec_path = "strategy_specs/drafts/fixture_pullback_15m.yaml"
    candidate = {
        "candidate_id": "C01",
        "path": "P1",
        "role": "return_ranking",
        "method": "linear_rank",
        "ablation": "baseline",
        "spec_path": spec_path,
        "data_contract": "data",
        "feature_contract": "features",
        "label_contract": "label",
        "validation_contract": "validation",
        "cost_contract": "cost",
        "benchmark_contract": "benchmark",
        "fallback": "flat",
    }
    manifest = {
        "schema_version": 1,
        "iter_id": "mom_minute_r1",
        "generated_before_backtest": True,
        "candidate_count": 1,
        "spec_hashes": {
            spec_path: "6d7a0ed38e20e4929cd13f439193aa87bba3a65834a7805f64aef4bbe2cbbb46"
        },
        "contracts": {
            "data": {"data": {}},
            "features": {"features": {}},
            "labels": {"label": {}},
            "validation": {"validation": {}},
            "costs": {"cost": {}},
            "benchmarks": {"benchmark": []},
        },
        "candidates": [candidate],
    }
    fixture_spec_path = sample_workspace / spec_path
    fixture_spec_path.write_text(
        fixture_spec_path.read_text(encoding="utf-8").replace(
            "  research_design:\n",
            "  research_design:\n"
            "    iter_id: mom_minute_r1\n"
            f"    candidate_manifest_path: {search['candidate_manifest_path']}\n"
            f"    data_feasibility_path: {search['data_feasibility_path']}\n",
            1,
        ),
        encoding="utf-8",
    )
    spec = load_strategy_spec(sample_workspace / spec_path)
    manifest["spec_hashes"][spec_path] = strategy_content_hash(spec)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    search["candidate_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    paths.search_space_json.write_text(json.dumps(search), encoding="utf-8")

    missing_prerequisites = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert "search_space_cost_table_path_missing" in missing_prerequisites.blocked
    assert "search_space_data_feasibility_path_missing" in missing_prerequisites.blocked
    feasibility = _write_candidate_feasibility(
        sample_workspace,
        paths,
        search,
        manifest,
        authorized=False,
    )
    rejected = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert "search_space_data_feasibility_not_authorized" in rejected.blocked
    feasibility["q2_diagnostic_execution_authorized"] = True
    _write_candidate_feasibility(
        sample_workspace,
        paths,
        search,
        manifest,
        payload=feasibility,
    )

    passed = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert passed.status == "ok"

    feasibility["candidate_accounting"]["diagnostic_runnable_count"] = 0
    _write_candidate_feasibility(
        sample_workspace,
        paths,
        search,
        manifest,
        payload=feasibility,
    )
    accounting_blocked = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert any(
        item.startswith("data_feasibility_accounting_diagnostic_runnable_count_mismatch")
        for item in accounting_blocked.blocked
    )

    manifest["candidates"][0]["label_contract"] = "missing"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    blocked = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert "candidate_manifest_sha256_mismatch" in blocked.blocked


def test_iteration_dossier_blocks_malformed_feasibility_contract(
    sample_workspace: Path,
) -> None:
    paths = init_iteration_dossier("mom_minute_r1", sample_workspace)
    _write_complete_pre_backtest_payload(paths)
    search = json.loads(paths.search_space_json.read_text(encoding="utf-8"))
    search["total_candidate_budget"] = 1
    search["paths"][0]["candidate_count"] = 1
    search["data_feasibility_path"] = "reports/research/control/mom-minute-data-feasibility.json"
    manifest_path = paths.root / "candidate-manifest.json"
    search["candidate_manifest_path"] = manifest_path.relative_to(sample_workspace).as_posix()
    spec_path = "strategy_specs/drafts/fixture_pullback_15m.yaml"
    fixture_spec_path = sample_workspace / spec_path
    fixture_spec_path.write_text(
        fixture_spec_path.read_text(encoding="utf-8").replace(
            "  research_design:\n",
            "  research_design:\n"
            "    iter_id: mom_minute_r1\n"
            f"    candidate_manifest_path: {search['candidate_manifest_path']}\n"
            f"    data_feasibility_path: {search['data_feasibility_path']}\n",
            1,
        ),
        encoding="utf-8",
    )
    manifest = _single_candidate_manifest(
        spec_path,
        strategy_content_hash(load_strategy_spec(fixture_spec_path)),
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    search["candidate_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    feasibility = _write_candidate_feasibility(
        sample_workspace,
        paths,
        search,
        manifest,
    )

    feasibility["q2_diagnostic_execution_authorized"] = "true"
    feasibility["research_pass"] = True
    feasibility["path_gates"]["P1"]["candidate_ids"] = ["WRONG"]
    _write_candidate_feasibility(
        sample_workspace,
        paths,
        search,
        manifest,
        payload=feasibility,
    )
    result = validate_iteration_dossier("mom_minute_r1", sample_workspace)

    assert "data_feasibility_q2_diagnostic_execution_authorized_not_boolean" in result.blocked
    assert "search_space_data_feasibility_not_authorized" in result.blocked
    assert "data_feasibility_diagnostic_scope_research_pass_must_be_false" in result.blocked
    assert "data_feasibility_P1_candidate_ids_mismatch" in result.blocked

    valid = _write_candidate_feasibility(
        sample_workspace,
        paths,
        search,
        manifest,
    )
    search["data_feasibility_sha256"] = "0" * 64
    paths.search_space_json.write_text(json.dumps(search), encoding="utf-8")
    hash_result = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert "data_feasibility_sha256_mismatch" in hash_result.blocked

    valid = _write_candidate_feasibility(
        sample_workspace,
        paths,
        search,
        manifest,
    )
    valid["q2_authorization"]["rows"][0]["candidate_binding_sha256"] = "0" * 64
    _write_candidate_feasibility(
        sample_workspace,
        paths,
        search,
        manifest,
        payload=valid,
    )
    candidate_hash_result = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert any(
        item.startswith("data_feasibility_q2_authorization_candidate_sha_mismatch")
        for item in candidate_hash_result.blocked
    )

    valid = _write_candidate_feasibility(
        sample_workspace,
        paths,
        search,
        manifest,
    )
    valid["q2_authorization"]["rows"][0]["evidence_sha256"] = "0" * 64
    _write_candidate_feasibility(
        sample_workspace,
        paths,
        search,
        manifest,
        payload=valid,
    )
    evidence_hash_result = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert any(
        item.startswith("data_feasibility_q2_authorization_evidence_sha_mismatch")
        for item in evidence_hash_result.blocked
    )

    _write_candidate_feasibility(sample_workspace, paths, search, manifest)
    fixture_spec_path.write_text(
        fixture_spec_path.read_text(encoding="utf-8").replace(
            f"data_feasibility_path: {search['data_feasibility_path']}",
            "data_feasibility_path: reports/research/control/wrong.json",
            1,
        ),
        encoding="utf-8",
    )
    manifest["spec_hashes"][spec_path] = strategy_content_hash(
        load_strategy_spec(fixture_spec_path)
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    search["candidate_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    paths.search_space_json.write_text(json.dumps(search), encoding="utf-8")
    spec_binding_result = validate_iteration_dossier("mom_minute_r1", sample_workspace)
    assert any(
        item.startswith("candidate_manifest_spec_feasibility_path_mismatch")
        for item in spec_binding_result.blocked
    )


def test_q2_execution_map_rejects_noncanonical_semantic_contracts(tmp_path: Path) -> None:
    manifest_by_id = {
        candidate_id: {
            "candidate_id": candidate_id,
            "path": "daily_deterministic" if candidate_id.startswith("D") else "daily_ml",
            "method": f"method_{candidate_id.lower()}",
            "feature_contract": "daily_price_volume_lag1",
            "label_contract": (
                "daily_downside_21d"
                if candidate_id in {"D11", "M05", "M06", "M07", "M08"}
                else "daily_rank_5d"
            ),
            "benchmark_contract": "daily_full_benchmark_family",
            "fallback": "cash",
        }
        for candidate_id in RUNNABLE_IDS
    }
    canonical = build_q2_execution_map({"candidates": list(manifest_by_id.values())})

    mutations = {
        "score": lambda payload: payload["rows"][0].__setitem__("score", "future_return_rank"),
        "feature_contract": lambda payload: payload["rows"][0].__setitem__(
            "feature_contract", "unregistered_features"
        ),
        "label_contract": lambda payload: payload["rows"][0].__setitem__(
            "label_contract", "future_label"
        ),
        "cost_contract": lambda payload: payload["rows"][0].__setitem__(
            "cost_contract", "zero_cost"
        ),
        "benchmark_contract": lambda payload: payload["rows"][0].__setitem__(
            "benchmark_contract", "incomplete_benchmarks"
        ),
        "primitive_fields": lambda payload: payload["rows"][0].__setitem__(
            "primitive_fields", ["open", "high", "low", "close", "volume"]
        ),
        "row_safety_flag": lambda payload: payload["rows"][0].__setitem__(
            "promotion_eligible", True
        ),
        "global_safety_flag": lambda payload: payload.__setitem__("forward_fill_allowed", True),
    }
    for mutation_name, mutate in mutations.items():
        payload = deepcopy(canonical)
        mutate(payload)
        path = tmp_path / f"q2-execution-map-{mutation_name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        blocked = _q2_execution_map_blockers(
            path,
            manifest_by_id,
            set(RUNNABLE_IDS),
            expected_iter_id="mom_stock_intraday_codesign_q1",
        )

        assert "q2_execution_map_canonical_contract_mismatch" in blocked, mutation_name


def test_execution_commands_enforce_declared_iteration_gate(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    spec_path = sample_workspace / "strategy_specs/drafts/fixture_pullback_15m.yaml"
    spec_path.write_text(
        spec_path.read_text(encoding="utf-8").replace(
            "  research_design:\n",
            "  research_design:\n    iter_id: missing_iteration_round\n",
            1,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    runner = CliRunner()

    results = [
        runner.invoke(app, ["backtest", str(spec_path)], catch_exceptions=False),
        runner.invoke(
            app,
            ["strategy", "optimize", str(spec_path)],
            catch_exceptions=False,
        ),
        runner.invoke(
            app,
            ["strategy", "parameter-sweep", str(spec_path)],
            catch_exceptions=False,
        ),
    ]

    assert all(result.exit_code != 0 for result in results)
    assert all("iteration dossier blocked" in result.output for result in results)


def test_execution_commands_block_top_level_search_without_iter_id(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    spec_path = sample_workspace / "strategy_specs/drafts/fixture_pullback_15m.yaml"
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    raw["research_design"] = {
        "parameter_space": {"risk.max_position_weight": [0.25, 0.5]},
        "candidate_budget": 2,
    }
    raw["notes"].pop("research_design", None)
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)

    result = CliRunner().invoke(
        app,
        ["backtest", str(spec_path)],
        catch_exceptions=False,
    )

    assert result.exit_code != 0
    assert "research_design requires iter_id" in result.output


@pytest.mark.parametrize(
    "research_design",
    [None, {"workflow_only_ungated_draft": True}],
)
def test_active_market_strategy_cannot_execute_without_iteration(
    sample_workspace: Path,
    research_design: dict[str, object] | None,
) -> None:
    spec_path = sample_workspace / "strategy_specs/drafts/fixture_pullback_15m.yaml"
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    raw["lifecycle"] = "active"
    raw["execution"]["mode"] = "paper_auto"
    raw["execution"]["broker"] = "alpaca_paper"
    raw["data"] = {"source": "alpaca", "symbol": "QQQ", "feed": "iex"}
    raw["data_assumptions"]["source"] = "alpaca"
    raw["notes"].pop("research_design", None)
    if research_design is None:
        raw.pop("research_design", None)
    else:
        raw["research_design"] = research_design
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="requires iter_id"):
        require_iteration_execution_gate(
            spec_path,
            sample_workspace,
            enforce_unbound_design=True,
        )


@pytest.mark.parametrize(
    "legacy_design",
    [
        {"workflow_only_ungated_draft": True},
        {
            "parameter_space": {"risk.max_position_weight": [0.25, 0.5]},
            "candidate_budget": 2,
        },
    ],
)
def test_active_market_strategy_cannot_bypass_gate_through_legacy_notes(
    sample_workspace: Path,
    legacy_design: dict[str, object],
) -> None:
    spec_path = sample_workspace / "strategy_specs/drafts/fixture_pullback_15m.yaml"
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    raw["lifecycle"] = "active"
    raw["execution"]["mode"] = "paper_auto"
    raw["execution"]["broker"] = "alpaca_paper"
    raw["data"] = {"source": "alpaca", "symbol": "QQQ", "feed": "iex"}
    raw["data_assumptions"]["source"] = "alpaca"
    raw.pop("research_design", None)
    raw["notes"]["research_design"] = legacy_design
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="requires iter_id"):
        require_iteration_execution_gate(
            spec_path,
            sample_workspace,
            enforce_unbound_design=True,
        )


def test_workflow_only_sample_draft_can_run_without_iteration(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    spec_path = sample_workspace / "strategy_specs/drafts/fixture_pullback_15m.yaml"
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    raw["research_design"] = {
        "workflow_only_ungated_draft": True,
        "parameter_space": {"risk.max_position_weight": [0.25, 0.5]},
        "candidate_budget": 2,
    }
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    monkeypatch.chdir(sample_workspace)

    result = CliRunner().invoke(
        app,
        ["backtest", str(spec_path)],
        catch_exceptions=False,
    )

    assert result.exit_code == 0


def test_research_design_binding_inventory_matches_independent_contract() -> None:
    assert RESEARCH_DESIGN_BINDING_FIELDS == EXPECTED_RESEARCH_DESIGN_BINDING_FIELDS


@pytest.mark.parametrize("binding_field", sorted(EXPECTED_RESEARCH_DESIGN_BINDING_FIELDS))
def test_workflow_only_sample_draft_cannot_carry_iteration_bindings(
    sample_workspace: Path,
    binding_field: str,
) -> None:
    spec_path = sample_workspace / "strategy_specs/drafts/fixture_pullback_15m.yaml"
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    raw["notes"].pop("research_design", None)
    raw["research_design"] = {
        "workflow_only_ungated_draft": True,
        binding_field: _research_binding_value(binding_field),
    }
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError):
        require_iteration_execution_gate(
            spec_path,
            sample_workspace,
            enforce_unbound_design=True,
            require_registered_iteration=True,
        )


@pytest.mark.parametrize("binding_field", sorted(EXPECTED_RESEARCH_DESIGN_BINDING_FIELDS))
def test_legacy_workflow_only_sample_draft_cannot_carry_iteration_bindings(
    sample_workspace: Path,
    binding_field: str,
) -> None:
    spec_path = sample_workspace / "strategy_specs/drafts/fixture_pullback_15m.yaml"
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    raw.pop("research_design", None)
    raw["notes"]["research_design"] = {
        "workflow_only_ungated_draft": True,
        binding_field: _research_binding_value(binding_field),
    }
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError):
        require_iteration_execution_gate(
            spec_path,
            sample_workspace,
            enforce_unbound_design=True,
            require_registered_iteration=True,
        )


@pytest.mark.parametrize("binding_field", sorted(EXPECTED_RESEARCH_DESIGN_BINDING_FIELDS))
def test_top_level_and_legacy_research_binding_conflicts_fail_closed(
    sample_workspace: Path,
    binding_field: str,
) -> None:
    spec_path = sample_workspace / "strategy_specs/drafts/fixture_pullback_15m.yaml"
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    raw["research_design"] = {binding_field: _research_binding_value(binding_field, "top")}
    raw["notes"]["research_design"] = {
        binding_field: _research_binding_value(binding_field, "legacy")
    }
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="conflicting top-level and notes.research_design"):
        require_iteration_execution_gate(spec_path, sample_workspace)


@pytest.mark.parametrize("binding_field", sorted(EXPECTED_RESEARCH_DESIGN_BINDING_FIELDS))
def test_identical_top_level_and_legacy_research_bindings_merge(
    sample_workspace: Path,
    binding_field: str,
) -> None:
    spec_path = sample_workspace / "strategy_specs/drafts/fixture_pullback_15m.yaml"
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    binding_value = _research_binding_value(binding_field)
    raw["research_design"] = {binding_field: binding_value}
    raw["notes"]["research_design"] = {binding_field: binding_value}
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    merged = research_design_mapping(load_strategy_spec(spec_path))

    assert merged[binding_field] == binding_value


def test_workflow_only_draft_cannot_bypass_gate_for_market_data(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    spec_path = sample_workspace / "strategy_specs/drafts/fixture_pullback_15m.yaml"
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    raw["research_design"] = {
        "workflow_only_ungated_draft": True,
        "parameter_space": {"risk.max_position_weight": [0.25, 0.5]},
        "candidate_budget": 2,
    }
    raw["data"] = {"source": "alpaca", "symbol": "QQQ", "feed": "iex"}
    raw["data_assumptions"]["source"] = "alpaca"
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)

    result = CliRunner().invoke(
        app,
        ["backtest", str(spec_path)],
        catch_exceptions=False,
    )

    assert result.exit_code != 0
    assert "research_design requires iter_id" in result.output


def test_iteration_binding_accepts_top_level_research_design(
    sample_workspace: Path,
) -> None:
    spec_path = sample_workspace / "strategy_specs/drafts/fixture_pullback_15m.yaml"
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    raw["research_design"] = {
        "iter_id": "mom_minute_r1",
        "candidate_manifest_path": (
            "reports/research/iterations/mom_minute_r1/candidate-manifest.json"
        ),
        "data_feasibility_path": "reports/research/iterations/mom_minute_r1/data-feasibility.json",
    }
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    spec = load_strategy_spec(spec_path)

    blocked = _spec_iteration_binding_blockers(
        spec,
        "strategy_specs/drafts/fixture_pullback_15m.yaml",
        {
            "iter_id": "mom_minute_r1",
            "candidate_manifest_path": (
                "reports/research/iterations/mom_minute_r1/candidate-manifest.json"
            ),
            "data_feasibility_path": (
                "reports/research/iterations/mom_minute_r1/data-feasibility.json"
            ),
        },
    )

    assert blocked == []


def test_generic_candidate_family_does_not_require_q2_diagnostic_contracts(
    sample_workspace: Path,
) -> None:
    iter_id = "mom_etf_structural_family_r9"
    iteration_root = sample_workspace / "reports" / "research" / "iterations" / iter_id
    iteration_root.mkdir(parents=True, exist_ok=True)
    manifest_rel = f"reports/research/iterations/{iter_id}/candidate-manifest.json"
    feasibility_rel = f"reports/research/iterations/{iter_id}/data-feasibility.json"
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "r9_d01.yaml"
    raw = yaml.safe_load(
        (sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["name"] = "r9_d01"
    raw["research_design"] = {
        "iter_id": iter_id,
        "candidate_manifest_path": manifest_rel,
        "data_feasibility_path": feasibility_rel,
    }
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    spec_ref = spec_path.relative_to(sample_workspace).as_posix()
    contract_groups = {
        "data": "data-contract",
        "features": "feature-contract",
        "labels": "label-contract",
        "validation": "validation-contract",
        "costs": "cost-contract",
        "benchmarks": "benchmark-contract",
    }
    contract_bindings = {}
    for group, contract_id in contract_groups.items():
        path = iteration_root / f"{contract_id}.json"
        path.write_text(json.dumps({"contract_id": contract_id}), encoding="utf-8")
        contract_bindings[group] = {
            contract_id: {
                "path": path.relative_to(sample_workspace).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        }
    candidate = {
        "candidate_id": "R9D01",
        "path": "monthly_core",
        "role": "control",
        "method": "monthly_spy_core",
        "ablation": "core_only",
        "spec_path": spec_ref,
        "fallback": "cash",
        "data_contract": "data-contract",
        "feature_contract": "feature-contract",
        "label_contract": "label-contract",
        "validation_contract": "validation-contract",
        "cost_contract": "cost-contract",
        "benchmark_contract": "benchmark-contract",
    }
    manifest = {
        "schema_version": 2,
        "manifest_type": "generic_candidate_family_v1",
        "iter_id": iter_id,
        "generated_before_backtest": True,
        "candidate_count": 1,
        "spec_hashes": {
            spec_ref: strategy_content_hash(load_strategy_spec(spec_path)),
        },
        "contracts": contract_bindings,
        "candidates": [candidate],
    }
    manifest_path = sample_workspace / manifest_rel
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    search = {
        "iter_id": iter_id,
        "candidate_manifest_path": manifest_rel,
        "candidate_manifest_contract": "generic_candidate_family_v1",
        "candidate_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "data_feasibility_path": feasibility_rel,
        "paths": [{"name": "monthly_core", "candidate_count": 1}],
    }
    assert (
        _candidate_manifest_blockers(
            manifest_path,
            search,
            sample_workspace,
            expected_total=1,
        )
        == []
    )

    required_references = {
        name: binding[next(iter(binding))] for name, binding in contract_bindings.items()
    }
    feasibility = {
        "schema_version": 2,
        "report_type": "generic_candidate_data_feasibility",
        "iter_id": iter_id,
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "historical_evaluation_authorized": True,
        "path_gates": {
            "monthly_core": {
                "action": "evaluate",
                "historical_evaluation_go": True,
                "candidate_ids": ["R9D01"],
            }
        },
        "candidate_accounting": {
            "frozen_candidate_count": 1,
            "evaluation_authorized_count": 1,
            "dependency_skipped_count": 0,
            "unresolved_count": 0,
            "balanced": True,
        },
        "candidate_authorization": {
            "candidate_count": 1,
            "rows": [
                {
                    "candidate_id": "R9D01",
                    "path": "monthly_core",
                    "action": "evaluate",
                    "reason_code": "complete_immutable_sip_panel",
                    "candidate_binding_sha256": hashlib.sha256(
                        json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest(),
                }
            ],
        },
        "required_reference_names": sorted(required_references),
        "required_references": required_references,
    }
    feasibility_path = sample_workspace / feasibility_rel
    feasibility_path.write_text(json.dumps(feasibility), encoding="utf-8")
    search["data_feasibility_sha256"] = hashlib.sha256(feasibility_path.read_bytes()).hexdigest()

    blocked = _data_feasibility_blockers(
        feasibility,
        feasibility_path,
        manifest_path,
        search,
        sample_workspace,
    )

    assert blocked == []


def test_policy_bound_manifest_rejects_policy_spec_and_phase_lock_drift(
    sample_workspace: Path,
) -> None:
    iter_id = "mom_breadth_policy_gate_r1"
    iteration_root = sample_workspace / "reports" / "research" / "iterations" / iter_id
    iteration_root.mkdir(parents=True, exist_ok=True)
    manifest_rel = f"reports/research/iterations/{iter_id}/candidate-manifest.json"
    feasibility_rel = f"reports/research/iterations/{iter_id}/data-feasibility.json"
    policy_rel = f"reports/research/iterations/{iter_id}/candidate-policy-contract.json"
    lock_rel = f"reports/research/iterations/{iter_id}/phase-one-preregistration-lock.json"

    policy = {
        "schema_version": 1,
        "policy_type": "absolute_trend_allocation",
        "feature_lag_sessions": 1,
        "fallback_symbol": "BIL",
    }
    policy_sha256 = hashlib.sha256(
        json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    policy_contract_id = f"{iter_id}_candidate_policies_v1"
    policy_path = sample_workspace / policy_rel
    policy_contract = {
        "schema_version": 1,
        "contract_id": policy_contract_id,
        "iter_id": iter_id,
        "generated_before_backtest": True,
        "policy_count": 1,
        "policies": [
            {
                "candidate_id": "TSM01",
                "method_variant": "monthly_absolute_trend_equal_risk",
                "factor_variant": "252_session_total_return_sign",
                "policy": policy,
                "policy_sha256": policy_sha256,
            }
        ],
    }
    policy_path.write_text(json.dumps(policy_contract), encoding="utf-8")

    spec_path = sample_workspace / "strategy_specs" / "drafts" / "breadth_tsm01.yaml"
    raw = yaml.safe_load(
        (sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["name"] = "breadth_tsm01"
    raw["research_design"] = {
        "iter_id": iter_id,
        "candidate_manifest_path": manifest_rel,
        "candidate_policy_contract_path": policy_rel,
        "data_feasibility_path": feasibility_rel,
        "preregistration_lock_path": lock_rel,
    }
    raw["notes"].update(
        {
            "candidate_id": "TSM01",
            "candidate_policy": policy,
            "candidate_policy_sha256": policy_sha256,
        }
    )
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    spec_rel = spec_path.relative_to(sample_workspace).as_posix()

    contract_bindings: dict[str, dict[str, dict[str, str]]] = {}
    for group, contract_id in {
        "data": "data-contract",
        "features": "feature-contract",
        "labels": "label-contract",
        "validation": "validation-contract",
        "costs": "cost-contract",
        "benchmarks": "benchmark-contract",
    }.items():
        path = iteration_root / f"{contract_id}.json"
        path.write_text(json.dumps({"contract_id": contract_id}), encoding="utf-8")
        contract_bindings[group] = {
            contract_id: {
                "path": path.relative_to(sample_workspace).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        }
    contract_bindings["candidate_policies"] = {
        policy_contract_id: {
            "path": policy_rel,
            "sha256": hashlib.sha256(policy_path.read_bytes()).hexdigest(),
        }
    }
    candidate = {
        "candidate_id": "TSM01",
        "path": "cross_asset_time_series_trend",
        "role": "deterministic_mechanism_candidate",
        "method": "monthly_absolute_trend_equal_risk",
        "ablation": "252_session_total_return_sign",
        "spec_path": spec_rel,
        "fallback": "BIL",
        "data_contract": "data-contract",
        "feature_contract": "feature-contract",
        "label_contract": "label-contract",
        "validation_contract": "validation-contract",
        "cost_contract": "cost-contract",
        "benchmark_contract": "benchmark-contract",
        "candidate_policy_contract": policy_contract_id,
        "candidate_policy_sha256": policy_sha256,
    }
    manifest = {
        "schema_version": 2,
        "manifest_type": "generic_candidate_family_v1",
        "iter_id": iter_id,
        "generated_before_backtest": True,
        "candidate_count": 1,
        "spec_hashes": {spec_rel: strategy_content_hash(load_strategy_spec(spec_path))},
        "contracts": contract_bindings,
        "candidates": [candidate],
    }
    manifest_path = sample_workspace / manifest_rel
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    lock_path = sample_workspace / lock_rel
    lock = {
        "schema_version": 1,
        "iter_id": iter_id,
        "generated_before_backtest": True,
        "generated_before_model_training": True,
        "candidate_ids": ["TSM01"],
        "candidate_policy_sha256": {"TSM01": policy_sha256},
        "immutable_inventory": {
            "candidate_policy_contract": {
                "path": policy_rel,
                "sha256": hashlib.sha256(policy_path.read_bytes()).hexdigest(),
            },
            "spec_TSM01": {
                "path": spec_rel,
                "sha256": hashlib.sha256(spec_path.read_bytes()).hexdigest(),
            },
        },
        "frozen_oos_read_authorized": False,
        "broker_writes": False,
    }
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    search = {
        "iter_id": iter_id,
        "candidate_manifest_path": manifest_rel,
        "candidate_manifest_contract": "generic_candidate_family_v1",
        "candidate_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "data_feasibility_path": feasibility_rel,
        "contracts": {"candidate_policy": policy_rel},
        "paths": [{"name": "cross_asset_time_series_trend", "candidate_count": 1}],
    }

    assert (
        _candidate_manifest_blockers(
            manifest_path,
            search,
            sample_workspace,
            expected_total=1,
        )
        == []
    )

    original_policy_bytes = policy_path.read_bytes()
    tampered_policy = deepcopy(policy_contract)
    tampered_policy["policies"][0]["policy"]["feature_lag_sessions"] = 0
    policy_path.write_text(json.dumps(tampered_policy), encoding="utf-8")
    policy_drift = _candidate_manifest_blockers(
        manifest_path,
        search,
        sample_workspace,
        expected_total=1,
    )
    assert any(item.endswith("TSM01_sha256_mismatch") for item in policy_drift)
    assert "candidate_manifest_phase_one_lock_candidate_policy_contract_sha256_mismatch" in (
        policy_drift
    )
    policy_path.write_bytes(original_policy_bytes)

    original_spec_bytes = spec_path.read_bytes()
    tampered_spec = yaml.safe_load(original_spec_bytes)
    tampered_spec["notes"]["candidate_policy"]["feature_lag_sessions"] = 0
    spec_path.write_text(yaml.safe_dump(tampered_spec, sort_keys=False), encoding="utf-8")
    manifest["spec_hashes"][spec_rel] = strategy_content_hash(load_strategy_spec(spec_path))
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    search["candidate_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    spec_drift = _candidate_manifest_blockers(
        manifest_path,
        search,
        sample_workspace,
        expected_total=1,
    )
    assert "candidate_manifest_TSM01_spec_candidate_policy_mismatch" in spec_drift
    assert "candidate_manifest_phase_one_lock_spec_TSM01_sha256_mismatch" in spec_drift
    spec_path.write_bytes(original_spec_bytes)
    manifest["spec_hashes"][spec_rel] = strategy_content_hash(load_strategy_spec(spec_path))
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    search["candidate_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    tampered_lock = deepcopy(lock)
    tampered_lock["candidate_policy_sha256"]["TSM01"] = "0" * 64
    lock_path.write_text(json.dumps(tampered_lock), encoding="utf-8")
    lock_drift = _candidate_manifest_blockers(
        manifest_path,
        search,
        sample_workspace,
        expected_total=1,
    )
    assert "candidate_manifest_phase_one_lock_candidate_policy_sha256_mismatch" in lock_drift


def test_iteration_dossier_cli_init_and_validate(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    runner = CliRunner()

    init_result = runner.invoke(
        app,
        ["research", "iteration", "init", "mom_minute_r1"],
        catch_exceptions=False,
    )
    validate_result = runner.invoke(
        app,
        ["research", "iteration", "validate", "mom_minute_r1"],
        catch_exceptions=False,
    )

    assert init_result.exit_code == 0
    assert validate_result.exit_code == 1
    assert "external_brief_sources_lt_8:0" in validate_result.output

    json_result = runner.invoke(
        app,
        ["research", "iteration", "validate", "mom_minute_r1", "--json"],
        catch_exceptions=False,
    )
    assert json_result.exit_code == 1
    assert json.loads(json_result.output)["status"] == "blocked"


def _single_candidate_manifest(spec_path: str, spec_hash: str) -> dict:
    return {
        "schema_version": 1,
        "iter_id": "mom_minute_r1",
        "generated_before_backtest": True,
        "candidate_count": 1,
        "spec_hashes": {spec_path: spec_hash},
        "contracts": {
            "data": {"data": {}},
            "features": {"features": {}},
            "labels": {"label": {}},
            "validation": {"validation": {}},
            "costs": {"cost": {}},
            "benchmarks": {"benchmark": []},
        },
        "candidates": [
            {
                "candidate_id": "C01",
                "path": "P1",
                "role": "return_ranking",
                "method": "linear_rank",
                "ablation": "baseline",
                "spec_path": spec_path,
                "data_contract": "data",
                "feature_contract": "features",
                "label_contract": "label",
                "validation_contract": "validation",
                "cost_contract": "cost",
                "benchmark_contract": "benchmark",
                "fallback": "flat",
            }
        ],
    }


def _write_candidate_feasibility(
    root: Path,
    paths,
    search: dict,
    manifest: dict,
    *,
    authorized: bool = True,
    payload: dict | None = None,
) -> dict:
    cost_path = root / search["cost_table_path"]
    cost_path.parent.mkdir(parents=True, exist_ok=True)
    if not cost_path.exists():
        cost_path.write_text("{}", encoding="utf-8")
    artifact_paths = {
        "parent_universe": paths.root / "parent-universe.json",
        "daily_panel": paths.root / "daily-panel-manifest.json",
        "intraday_panel": paths.root / "intraday-panel-manifest.json",
        "cost_contract": cost_path,
        "q2_execution_map": paths.root / "q2-execution-map.json",
    }
    for field_name, artifact_path in artifact_paths.items():
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        if field_name == "q2_execution_map":
            execution_rows = []
            for candidate in manifest["candidates"]:
                execution_rows.append(
                    {
                        "candidate_id": candidate["candidate_id"],
                        "path": candidate["path"],
                        "method": candidate["method"],
                        "candidate_binding_sha256": hashlib.sha256(
                            json.dumps(
                                candidate,
                                sort_keys=True,
                                separators=(",", ":"),
                            ).encode()
                        ).hexdigest(),
                        "primitive_fields": ["open", "close", "volume"],
                        "research_pass": False,
                        "paper_ready_pass": False,
                        "promotion_eligible": False,
                        "required_benchmarks": ["ex_post_best_symbol_report_only"],
                    }
                )
            artifact_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "iter_id": "mom_minute_r1",
                        "scope": "historical_current_universe_diagnostic",
                        "survivorship_labelled": True,
                        "runnable_candidate_count": len(execution_rows),
                        "primitive_field_allowlist": ["open", "close", "volume"],
                        "high_low_dependent_candidates_allowed": False,
                        "forward_fill_allowed": False,
                        "zero_return_substitution_allowed": False,
                        "rows": execution_rows,
                    }
                ),
                encoding="utf-8",
            )
        elif not artifact_path.exists():
            artifact_path.write_text("{}", encoding="utf-8")
    if payload is None:
        candidate_ids = [str(row["candidate_id"]) for row in manifest["candidates"]]
        daily_evidence_path = artifact_paths["daily_panel"]
        payload = {
            "schema_version": 1,
            "report_type": "test_data_feasibility",
            "iter_id": "mom_minute_r1",
            "workflow_pass": True,
            "research_pass": False,
            "llm_contribution_pass": False,
            "paper_ready_pass": False,
            "q2_diagnostic_execution_authorized": authorized,
            "path_gates": {
                "P1": {
                    "q2_action": "run_diagnostic",
                    "historical_diagnostic_go": True,
                    "historical_research_qualified": False,
                    "candidate_ids": candidate_ids,
                }
            },
            "candidate_accounting": {
                "frozen_candidate_count": len(candidate_ids),
                "diagnostic_runnable_count": len(candidate_ids),
                "dependency_skipped_count": 0,
                "unresolved_count": 0,
                "balanced": True,
            },
            "q2_authorization": {
                "candidate_count": len(candidate_ids),
                "rows": [
                    {
                        "candidate_id": str(candidate["candidate_id"]),
                        "path": str(candidate["path"]),
                        "action": "run_diagnostic",
                        "reason_code": "test_diagnostic_gate",
                        "candidate_binding_sha256": hashlib.sha256(
                            json.dumps(
                                candidate,
                                sort_keys=True,
                                separators=(",", ":"),
                            ).encode()
                        ).hexdigest(),
                        "evidence_path": daily_evidence_path.relative_to(root).as_posix(),
                        "evidence_sha256": hashlib.sha256(
                            daily_evidence_path.read_bytes()
                        ).hexdigest(),
                    }
                    for candidate in manifest["candidates"]
                ],
            },
        }
    for field_name, artifact_path in artifact_paths.items():
        payload[field_name] = {
            "path": artifact_path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
        }
    feasibility_path = root / search["data_feasibility_path"]
    feasibility_path.parent.mkdir(parents=True, exist_ok=True)
    feasibility_path.write_text(json.dumps(payload), encoding="utf-8")
    search["data_feasibility_sha256"] = hashlib.sha256(feasibility_path.read_bytes()).hexdigest()
    paths.search_space_json.write_text(json.dumps(search), encoding="utf-8")
    return payload


def _test_binding(path: Path, root: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
    }


def _write_multimodal_final_receipt_fixture(root: Path, *, round_number: int):
    round_id = f"r{round_number}"
    round_label = f"R{round_number}"
    iter_id = f"mom_multiasset_forward_multimodal_{round_id}"
    paths = iteration_dossier_paths(iter_id, root)
    evaluation_dir = paths.root / "evaluation-run"
    lock_dir = paths.root / "lock-set"
    evaluation_dir.mkdir(parents=True)
    lock_dir.mkdir()

    lock_paths = {
        "preregistration_lock": lock_dir / "preregistration-lock.json",
        "runner_lock": lock_dir / "runner-lock.json",
        "lock_anchor": lock_dir / "lock-anchor.json",
    }
    preregistration = {
        "schema_version": 1,
        "iter_id": iter_id,
        "status": f"behavior_contracts_locked_before_first_{round_id}_price_calculation",
    }
    runner = {
        "schema_version": 1,
        "iter_id": iter_id,
        "status": f"implementation_locked_before_first_{round_id}_price_calculation",
    }
    harness_reconciliation = None
    if round_number == 5:
        candidate_ids = [
            "R5D01",
            "R5D02",
            "R5M01",
            "R5M02",
            "R5L01",
            "R5C01",
            "R5F01",
            "R5P01",
        ]
        config_paths = {
            "risk_domains": root / "harness/risk_domains.yaml",
            "artifact_contracts": root / "harness/artifact_contracts.yaml",
            "skill_manifest": root / "harness/skill_manifest.yaml",
        }
        for label, path in config_paths.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"fixture: {label}\n", encoding="utf-8")
        harness_artifacts = [_test_binding(path, root) for path in config_paths.values()]
        spec_bindings = []
        candidate_rows = {}
        binding_templates = {
            "plan_json": "reports/harness/plans/{strategy}.json",
            "plan_markdown": "reports/harness/plans/{strategy}.md",
            "execution_policy": "reports/harness/execution/{strategy}-execution-policy.json",
            "execution_reality": ("reports/harness/execution/{strategy}-execution-reality.json"),
            "execution_reality_markdown": (
                "reports/harness/execution/{strategy}-execution-reality.md"
            ),
            "source_cards": "reports/harness/source_cards/{strategy}.jsonl",
            "verify_receipt": "reports/harness/verify/{strategy}.json",
        }
        for candidate_id in candidate_ids:
            strategy_name = f"us_multiasset_forward_mm_r5_{candidate_id[2:].lower()}"
            spec_path = root / f"strategy_specs/drafts/{strategy_name}.yaml"
            spec_path.parent.mkdir(parents=True, exist_ok=True)
            spec_path.write_text(f"name: {strategy_name}\n", encoding="utf-8")
            spec_file_sha256 = hashlib.sha256(spec_path.read_bytes()).hexdigest()
            spec_semantic_sha256 = hashlib.sha256(
                f"semantic:{strategy_name}".encode("ascii")
            ).hexdigest()
            spec_bindings.append(
                {
                    "candidate_id": candidate_id,
                    "path": spec_path.relative_to(root).as_posix(),
                    "file_sha256": spec_file_sha256,
                    "semantic_sha256": spec_semantic_sha256,
                }
            )
            bindings = {}
            for label, template in binding_templates.items():
                artifact_path = root / template.format(strategy=strategy_name)
                artifact_path.parent.mkdir(parents=True, exist_ok=True)
                artifact_path.write_text(
                    json.dumps({"candidate_id": candidate_id, "artifact": label}) + "\n",
                    encoding="utf-8",
                )
                binding = _test_binding(artifact_path, root)
                bindings[label] = binding
                harness_artifacts.append(binding)
            candidate_rows[candidate_id] = {
                "candidate_id": candidate_id,
                "strategy_name": strategy_name,
                "spec_path": spec_path.relative_to(root).as_posix(),
                "spec_file_sha256": spec_file_sha256,
                "spec_semantic_sha256": spec_semantic_sha256,
                "risk_domains": ["daily_open_execution"],
                "required_skills": ["execution-reality-reviewer", "source-researcher"],
                "required_artifacts": [
                    "execution_policy",
                    "execution_reality_report",
                    "source_cards",
                ],
                "blocking_rule_ids": [
                    "naked_market_order_must_be_justified",
                    "compare_at_least_two_execution_methods",
                ],
                "structural_research_harness_pass": True,
                "empirical_execution_evidence_pass": False,
                "paper_readiness_evidence_pass": False,
                "bindings": bindings,
            }
        harness_reconciliation = {
            "schema_version": 1,
            "reconciliation_contract": (
                "multiasset_forward_multimodal_r5_harness_reconciliation_v1"
            ),
            "iter_id": iter_id,
            "stage": "research",
            "evidence_scope": (
                "spec_bound_execution_policy_source_research_and_deterministic_stress_contract_only"
            ),
            "candidate_count": len(candidate_ids),
            "contract_bindings": {
                label: _test_binding(path, root) for label, path in config_paths.items()
            },
            "candidates": candidate_rows,
            "research_gate_pass": True,
            "empirical_execution_evidence_pass": False,
            "paper_readiness_evidence_pass": False,
            "limitations": [
                "generated deterministic scenarios remain placeholders",
                "historical assumptions do not attest fills or capacity",
                "matched Alpaca Paper TCA remains mandatory",
            ],
        }
        preregistration.update(
            {
                "artifacts": harness_artifacts,
                "specs": spec_bindings,
                "harness_reconciliation": harness_reconciliation,
            }
        )
    lock_paths["preregistration_lock"].write_text(json.dumps(preregistration), encoding="utf-8")
    lock_paths["runner_lock"].write_text(json.dumps(runner), encoding="utf-8")
    anchor_subject = {
        "iter_id": iter_id,
        "preregistration_lock_sha256": hashlib.sha256(
            lock_paths["preregistration_lock"].read_bytes()
        ).hexdigest(),
        "runner_lock_sha256": hashlib.sha256(lock_paths["runner_lock"].read_bytes()).hexdigest(),
    }
    operator_anchor_sha256 = hashlib.sha256(
        json.dumps(anchor_subject, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    lock_anchor = {
        "schema_version": 1,
        **anchor_subject,
        "operator_lock_anchor_sha256": operator_anchor_sha256,
    }
    if round_number == 5:
        lock_anchor["external_custody_required"] = True
    lock_paths["lock_anchor"].write_text(json.dumps(lock_anchor), encoding="utf-8")

    support_paths = {
        "candidate_manifest": paths.root / "candidate-manifest.json",
        "data_contract": paths.root / "data-contract.json",
        "data_manifest": paths.root / "bound-data-manifest.json",
        "parent_snapshot_binding": paths.root / "parent-snapshot-binding.json",
    }
    for label, path in support_paths.items():
        path.write_text(json.dumps({"artifact": label, "iter_id": iter_id}), encoding="utf-8")

    attempt_path = paths.root / "evaluation-attempt.json"
    attempt = {
        "schema_version": 1,
        "iter_id": iter_id,
        "status": "reserved_before_first_price_parse",
        "reserved_at": "2026-07-29T00:00:00+00:00",
        "operator_lock_anchor_sha256": operator_anchor_sha256,
        "preregistration_lock_sha256": anchor_subject["preregistration_lock_sha256"],
        "runner_lock_sha256": anchor_subject["runner_lock_sha256"],
        "data_manifest_sha256": hashlib.sha256(
            support_paths["data_manifest"].read_bytes()
        ).hexdigest(),
        "rerun_policy": "any_existing_attempt_blocks_all_future_evaluation_attempts",
    }
    if round_number == 5:
        attempt["lock_custody_receipt_sha256"] = "c" * 64
        attempt["lock_custody_bundle_sha256"] = "d" * 64
    attempt_path.write_text(json.dumps(attempt), encoding="utf-8")
    attempt_binding = _test_binding(attempt_path, root)
    preflight = {
        "status": "ok",
        "dossier_checked_at": "2026-07-29T00:00:00+00:00",
        "preregistration_lock_path": lock_paths["preregistration_lock"]
        .relative_to(root)
        .as_posix(),
        "preregistration_lock_sha256": anchor_subject["preregistration_lock_sha256"],
        "runner_lock_path": lock_paths["runner_lock"].relative_to(root).as_posix(),
        "runner_lock_sha256": anchor_subject["runner_lock_sha256"],
        "lock_anchor_path": lock_paths["lock_anchor"].relative_to(root).as_posix(),
        "lock_anchor_file_sha256": hashlib.sha256(
            lock_paths["lock_anchor"].read_bytes()
        ).hexdigest(),
        "operator_lock_anchor_sha256": operator_anchor_sha256,
        "evaluation_attempt": attempt_binding,
    }
    if round_number == 5:
        preflight["lock_custody_receipt_sha256"] = attempt["lock_custody_receipt_sha256"]
        preflight["lock_custody_bundle_sha256"] = attempt["lock_custody_bundle_sha256"]
    for label, path in support_paths.items():
        preflight[f"{label}_path"] = path.relative_to(root).as_posix()
        preflight[f"{label}_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    if harness_reconciliation is not None:
        preflight["harness_reconciliation_sha256"] = hashlib.sha256(
            json.dumps(
                harness_reconciliation,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("ascii")
        ).hexdigest()

    child_filenames = {
        "feature_ledger": "feature-ledger.jsonl",
        "prediction_ledger": "prediction-ledger.jsonl",
        "daily_return_ledger": "daily-return-ledger.jsonl",
        "target_ledger": "target-ledger.jsonl",
        "event_ledger": "cost-event-ledger.jsonl",
        "benchmark_ledger": "benchmark-ledger.jsonl",
        "model_ledger": "model-ledger.jsonl",
        "trial_ledger": "trial-ledger.jsonl",
        "cost_reconciliation": "cost-reconciliation.json",
        "model_provenance": "model-provenance.json",
        "evaluation": "evaluation-report.json",
        "evaluation_markdown": "evaluation-report.md",
        "decision_record": "decision-record.md",
    }
    child_paths = {name: evaluation_dir / filename for name, filename in child_filenames.items()}
    evaluation = {
        "schema_version": 1,
        "iter_id": iter_id,
        "report_type": f"multiasset_forward_multimodal_{round_id}_matched_transfer_evaluation",
        "decision": f"stop_{round_id}",
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "preflight": preflight,
        "fallback_identity": {f"{round_label}F01_equals_{round_label}M01": True},
        "cost_reconciliation": {"pass": True},
        "benchmarks": {"complete": True},
        "evidence_reconciliation": {"staged_ledger_verification": {"pass": True}},
    }
    if harness_reconciliation is not None:
        evaluation["harness_reconciliation"] = harness_reconciliation
    for name, path in child_paths.items():
        if name == "evaluation":
            content = json.dumps(evaluation)
        elif name == "evaluation_markdown":
            content = f"# {round_label} Evaluation\n\nFinal matched-transfer evaluation evidence.\n"
        elif name == "decision_record":
            content = _decision_record_md("stop")
        elif path.suffix == ".jsonl":
            content = json.dumps({"schema_version": 1, "iter_id": iter_id}) + "\n"
        else:
            content = json.dumps({"schema_version": 1, "iter_id": iter_id})
        path.write_text(content, encoding="utf-8")

    receipt = {
        "schema_version": 3,
        "receipt_contract": f"multiasset_forward_multimodal_{round_id}_v3",
        "iter_id": iter_id,
        "evidence_publication_status": "complete",
        "decision": f"stop_{round_id}",
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "children": {name: _test_binding(path, root) for name, path in child_paths.items()},
        **{name: _test_binding(path, root) for name, path in lock_paths.items()},
        "evaluation_attempt": attempt_binding,
        "prepublication_checks": {
            "prebacktest_dossier_status": "ok",
            "workflow_pass": True,
            "fallback_identity": True,
            "cost_reconciliation_pass": True,
            "benchmark_family_complete": True,
            "staged_ledger_verification_pass": True,
        },
    }
    if harness_reconciliation is not None:
        receipt["prepublication_checks"]["harness_reconciliation_pass"] = True
    receipt_path = evaluation_dir / "evaluation-receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    if round_number == 5:
        anchor_path = evaluation_dir / "evaluation-anchor.json"
        anchor_subject = {
            "schema_version": 1,
            "anchor_contract": "multiasset_forward_multimodal_r5_evaluation_anchor_v1",
            "iter_id": iter_id,
            "status": "complete_for_external_hash_custody",
            "anchor_path": anchor_path.relative_to(root).as_posix(),
            "receipt": _test_binding(receipt_path, root),
            **{name: _test_binding(path, root) for name, path in lock_paths.items()},
            "evaluation_attempt": attempt_binding,
            "operator_lock_anchor_sha256": operator_anchor_sha256,
            "custody_requirement": (
                "record_evaluation_anchor_file_sha256_and_operator_subject_sha256_"
                "outside_the_mutable_worktree"
            ),
            "local_read_only_mode_is_not_independent_custody": True,
        }
        anchor = {
            **anchor_subject,
            "operator_evaluation_anchor_sha256": hashlib.sha256(
                json.dumps(
                    anchor_subject,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                ).encode("ascii")
            ).hexdigest(),
        }
        anchor_path.write_bytes(
            json.dumps(
                anchor,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("ascii")
            + b"\n"
        )
        anchor_path.chmod(0o400)
    return paths, receipt_path, receipt, child_paths, lock_paths


def _write_r4_final_receipt_fixture(root: Path):
    return _write_multimodal_final_receipt_fixture(root, round_number=4)


def _write_r5_final_receipt_fixture(root: Path):
    return _write_multimodal_final_receipt_fixture(root, round_number=5)


def _minimal_campaign_contract(*, child_iteration_ids: list[str]) -> dict:
    descriptor = {
        "economic_mechanism": "Cross-asset trend persistence",
        "universe_or_asset_class": "Long-lived US ETFs",
        "horizon": "One to twelve months",
        "data_modality": "Lagged daily prices and volume",
        "portfolio_construction": "Volatility-scaled long-only allocation",
        "execution_style": "Scheduled next-open rebalance with cost stress",
        "universe_selection": "fixed_long_lived",
        "role": "research",
    }
    return {
        "schema_version": 1,
        "campaign_id": "campaign_gate_r1",
        "created_at": "2026-08-15T17:00:00Z",
        "title": "Iteration campaign gate fixture",
        "objective": "Prove campaign identity is bound before any child backtest.",
        "parent_iteration_ids": ["prior_iteration"],
        "child_iteration_ids": child_iteration_ids,
        "root_hypothesis_id": "H0",
        "hypotheses": [
            {
                "hypothesis_id": "H0",
                "parent_hypothesis_id": None,
                **descriptor,
                "promotion_eligible": False,
            },
            {
                "hypothesis_id": "H1",
                "parent_hypothesis_id": "H0",
                **descriptor,
                "promotion_eligible": True,
            },
        ],
        "branch_quotas": [
            {
                "branch_id": "B1",
                "hypothesis_id": "H1",
                "min_candidates": 12,
                "max_candidates": 12,
            }
        ],
        "candidate_blueprints": [
            {
                "candidate_id": f"C{index:02d}",
                "hypothesis_id": "H1",
                "branch_id": "B1",
                "child_iteration_id": child_iteration_ids[0],
                "method_variant": f"method_{index}",
                "factor_variant": f"factor_{index}",
                "archive_descriptors": {
                    "economic_mechanism": "trend",
                    "horizon": f"horizon_{index}",
                },
                "model_training": False,
                "promotion_eligible": True,
            }
            for index in range(1, 13)
        ],
        "visibility_partitions": [
            {
                "partition_id": "train",
                "kind": "development",
                "allowed_operations": ["candidate_generation", "model_training"],
            },
            {
                "partition_id": "development",
                "kind": "development",
                "allowed_operations": [
                    "candidate_pruning",
                    "resource_allocation",
                    "archive_update",
                ],
            },
            {
                "partition_id": "frozen_oos",
                "kind": "frozen_oos",
                "allowed_operations": ["promotion_evaluation", "reporting"],
            },
        ],
        "exposure_budgets": {
            "candidate_budget": 12,
            "cumulative_trial_exposure_budget": 12,
        },
        "exploration_policy": {
            "generation_mode": "enumerated_candidates",
            "mutation_mode": "none",
        },
        "qd_archive": {
            "cell_key_fields": ["economic_mechanism", "horizon"],
            "quality_metric": "development_cost_stressed_sharpe",
            "quality_direction": "maximize",
            "quality_partition_id": "development",
            "tie_break_rules": [{"field": "candidate_id", "direction": "ascending"}],
            "max_elites_per_cell": 1,
        },
        "statistical_family_policy": {
            "primary_sharpe_minimum": 1.0,
            "primary_sharpe_operator": ">",
            "advancing_pair_correlation": {
                "method": "pearson",
                "return_stream": (
                    "development_validation_continuous_daily_primary_20bps_terminal_free"
                ),
                "absolute_maximum": 0.70,
                "operator": "<=",
                "minimum_passing_pair_count": 1,
            },
            "dsr_minimum": 0.75,
            "pbo_maximum": 0.4,
            "spa_p_value_maximum": 0.05,
            "dsr_hac_lag": 21,
            "pbo_block_count": 8,
            "pbo_in_sample_block_count": 4,
            "spa_block_length": 21,
            "spa_resample_count": 2000,
            "spa_seed": 4201,
        },
        "candidate_promotion_policy": {
            "primary_cost_bps": 20,
            "stress_cost_bps": 40,
            "annualization_sessions": 252,
            "cagr_excess_qqq_minimum": 0.08,
            "qqq_capture_ratio_minimum": 1.0,
            "qqq_downside_capture_maximum": 1.5,
            "max_drawdown_minimum": -0.65,
            "mar_minimum": 0.4,
            "chronological_fold_count": 4,
            "minimum_positive_folds": 3,
            "development_partition_id": "development",
            "development_fold_ids": ["D1", "D2", "D3", "D4"],
            "stress_total_return_minimum": 0.0,
            "stress_total_return_operator": ">",
            "required_benchmark_roles": [
                "same_symbol_buy_and_hold",
                "equal_weight_universe",
                "market_proxy",
                "growth_proxy",
                "sector_theme_proxy",
                "cash_proxy",
                "leveraged_growth_proxy",
                "ex_post_best_symbol",
            ],
        },
        "expensive_resource_rungs": [],
        "promotion_evidence": None,
    }


def _write_complete_pre_backtest_payload(paths) -> None:
    sources = [
        {
            "url": f"https://example.com/source-{idx}",
            "published_or_updated_at": "2026-01-01",
            "source_type": "paper" if idx < 3 else "platform_docs",
            "credibility": "high",
            "core_claim": f"claim {idx}",
            "project_applicability": "Defines a bounded minute momentum hypothesis.",
            "reflection": "May decay and is sensitive to transaction costs.",
        }
        for idx in range(8)
    ]
    paths.external_brief_json.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "iter_id": "mom_minute_r1",
                "strategy_name": "us_minute_momentum",
                "source_spec_path": None,
                "spec_hash": None,
                "objective": "US minute momentum round 1",
                "sources": sources,
                "topic_coverage": [
                    "intraday momentum",
                    "intraday reversal",
                    "cross-sectional momentum",
                    "overnight intraday decomposition",
                    "volatility-managed momentum",
                    "transaction costs",
                ],
                "candidate_matrix_revisions": [{"path": "P1", "decision": "keep"}],
                "hypothesis_links": [{"hypothesis_id": "H1", "source_urls": [sources[0]["url"]]}],
            }
        ),
        encoding="utf-8",
    )
    paths.search_space_json.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "iter_id": "mom_minute_r1",
                "strategy_name": "us_minute_momentum",
                "source_spec_path": None,
                "spec_hash": None,
                "total_candidate_budget": 12,
                "paths": [
                    {
                        "name": "P1",
                        "candidate_count": 12,
                        "hypothesis_refs": ["H1"],
                        "parameters": {"lookback": [12, 24]},
                        "benchmark_family": ["QQQ", "BIL", "naive_momentum"],
                    }
                ],
                "trial_ledger_paths": [],
                "evaluation_report_paths": [],
                "cost_table_path": "reports/research/control/minute-momentum-feasibility.json",
                "data_feasibility_path": "reports/research/control/minute-momentum-feasibility.md",
            }
        ),
        encoding="utf-8",
    )
    paths.external_brief_md.write_text(_filled_md("External brief"), encoding="utf-8")
    paths.hypotheses_md.write_text(_hypotheses_md(), encoding="utf-8")
    paths.search_space_md.write_text(_filled_md("Search space"), encoding="utf-8")
    paths.decision_record_md.write_text(_decision_record_md("pending"), encoding="utf-8")


def _filled_md(title: str) -> str:
    return (
        f"# {title}\n\n"
        "This file has been completed with enough project-specific content to move beyond "
        "the generated template. It records the hypothesis, evidence linkage, benchmark "
        "family, cost caveats, expected failure mode, and the next decision for the "
        "Open Composer minute momentum iteration.\n"
    )


def _hypotheses_md() -> str:
    return """# Hypotheses

## H1

- Hypothesis: Thirty-minute ETF momentum persists after the opening range when
  trend breadth is positive.
- Failure mode: The signal reverses after costs or only works in a single
  recent bull regime.
- Measurement: Four chronological walk-forward folds with QQQ, SPY, BIL,
  equal-weight universe, and naive momentum benchmarks.
- Stop/Pivot criterion: Stop if the last two folds are negative after baseline
  costs; pivot to lower frequency if cost stress dominates.
"""


def _decision_record_md(decision: str) -> str:
    return f"""# Decision Record

## P1

- Path: time-series ETF momentum.
- Decision: {decision}
- Reason: Pre-backtest dossier is ready when pending; final records must use
  continue, pivot, or stop with supporting evidence.
- Next iteration suggestion: Move to ML only if OOS decisions exceed the sample
  threshold and the non-ML baseline survives cost stress.
"""
