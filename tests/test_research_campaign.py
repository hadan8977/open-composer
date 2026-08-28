from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
import typer
from pydantic import ValidationError
from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.models.strategy_spec import ResearchDesign
from open_composer.research.campaign import (
    CAMPAIGN_FILENAME,
    MIN_DSR_STREAM_ROWS,
    QQQ_ORTHOGONALITY_CORRELATION_THRESHOLD,
    ResearchCampaignContract,
    campaign_contract_path,
    effective_trial_count_from_ledger,
    family_effective_trial_count_from_ledger,
    load_campaign_contract,
    recompute_candidate_promotion_metrics,
    validate_campaign_contract,
)
from open_composer.research.campaign_statistics import recompute_campaign_statistics
from open_composer.research.design_contract import research_design_requires_iteration_gate
from open_composer.research.quality_diversity import (
    QualityDiversityCandidate,
    append_allocation_entry,
    build_quality_diversity_archive,
    initialize_allocation_ledger,
    quality_diversity_policy_from_campaign,
)
from scripts.prepare_mom_breadth_qd_r1 import (
    CAMPAIGN_PATH as MOM_BREADTH_CAMPAIGN_PATH,
)
from scripts.prepare_mom_breadth_qd_r1 import (
    TRIAL_ACCOUNTING_IDENTITY_KEYS,
    _candidate_manifest_payload,
    _cumulative_trial_contract,
    _search_space,
    _trial_accounting_identity,
    _validation_contract,
)


def _hypothesis(
    hypothesis_id: str,
    parent_hypothesis_id: str | None,
    *,
    universe_selection: str = "point_in_time",
    role: str = "research",
    promotion_eligible: bool = True,
) -> dict[str, Any]:
    return {
        "hypothesis_id": hypothesis_id,
        "parent_hypothesis_id": parent_hypothesis_id,
        "economic_mechanism": f"Independent economic mechanism for {hypothesis_id}",
        "universe_or_asset_class": "Point-in-time US equities and long-lived ETFs",
        "horizon": "One to twelve months",
        "data_modality": "Price, volume, and volatility",
        "portfolio_construction": "Volatility-scaled long-only ranking portfolio",
        "execution_style": "Scheduled next-open rebalance with cost stress",
        "universe_selection": universe_selection,
        "role": role,
        "promotion_eligible": promotion_eligible,
    }


def _passing_contract() -> dict[str, Any]:
    branch_ids = [f"H{index}" for index in range(1, 7)]
    hypotheses = [_hypothesis("H0", None)] + [
        _hypothesis(hypothesis_id, "H0") for hypothesis_id in branch_ids
    ]
    hypotheses[-1] = _hypothesis(
        "H6",
        "H0",
        universe_selection="static_hotspot_control",
        role="control",
        promotion_eligible=False,
    )
    candidate_blueprints = [
        {
            "candidate_id": f"H{branch_index}C{candidate_index:02d}",
            "hypothesis_id": f"H{branch_index}",
            "branch_id": f"B{branch_index}",
            "child_iteration_id": f"momentum_branch_r{branch_index}",
            "method_variant": f"method_{candidate_index}",
            "factor_variant": f"factor_{candidate_index}",
            "archive_descriptors": {
                "mechanism_family": f"mechanism_{branch_index}",
                "turnover_bucket": ["low", "medium", "high"][candidate_index - 1],
                "beta_bucket": "control" if branch_index == 6 else "market",
            },
            "model_training": False,
            "promotion_eligible": branch_index != 6,
        }
        for branch_index in range(1, 7)
        for candidate_index in range(1, 4)
    ]
    return {
        "schema_version": 1,
        "campaign_id": "momentum_qd_r1",
        "created_at": "2026-08-15T17:00:00Z",
        "title": "Broad momentum quality-diversity campaign",
        "objective": "Find orthogonal momentum mechanisms under one fixed protocol.",
        "parent_iteration_ids": ["momentum_baseline_r0"],
        "child_iteration_ids": [f"momentum_branch_r{index}" for index in range(1, 7)],
        "root_hypothesis_id": "H0",
        "hypotheses": hypotheses,
        "branch_quotas": [
            {
                "branch_id": f"B{index}",
                "hypothesis_id": f"H{index}",
                "min_candidates": 2,
                "max_candidates": 3,
            }
            for index in range(1, 7)
        ],
        "candidate_blueprints": candidate_blueprints,
        "visibility_partitions": [
            {
                "partition_id": "development_train",
                "kind": "development",
                "allowed_operations": [
                    "candidate_generation",
                    "candidate_mutation",
                    "model_training",
                ],
            },
            {
                "partition_id": "development_validation",
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
            {
                "partition_id": "challenge_set",
                "kind": "challenge",
                "allowed_operations": ["promotion_evaluation", "reporting"],
            },
            {
                "partition_id": "forward_observation",
                "kind": "forward",
                "allowed_operations": ["reporting"],
            },
        ],
        "exposure_budgets": {
            "candidate_budget": 18,
            "cumulative_trial_exposure_budget": 54,
        },
        "exploration_policy": {
            "generation_mode": "deterministic_template_expansion",
            "mutation_mode": "bounded_parameter_mutation",
        },
        "qd_archive": {
            "cell_key_fields": ["mechanism_family", "turnover_bucket", "beta_bucket"],
            "quality_metric": "development_cost_stressed_sharpe",
            "quality_direction": "maximize",
            "quality_partition_id": "development_validation",
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
            "development_partition_id": "development_validation",
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
        "expensive_resource_rungs": [
            {
                "rung_id": "ML1",
                "order": 1,
                "resource_kind": "ml_training",
                "input_candidate_limit": 18,
                "survivor_limit": 6,
                "read_partition_ids": ["development_train", "development_validation"],
                "ranking_metric": "development_incremental_utility",
                "tie_break_rules": [
                    {"field": "calibration_error", "direction": "ascending"},
                    {"field": "candidate_id", "direction": "ascending"},
                ],
            }
        ],
        "promotion_evidence": {
            "promotion_cohort_ref": "artifacts/promotion-cohort.json",
            "pre_oos_seal_ref": "artifacts/pre-oos-seal.json",
            "common_return_matrix_ref": "artifacts/common-return-matrix.json",
            "statistical_family_gate_ref": "artifacts/statistical-family-gates.json",
            "candidate_promotion_gate_ref": "artifacts/candidate-promotion-gates.json",
        },
    }


def _nineteen_candidate_contract() -> dict[str, Any]:
    payload = _passing_contract()
    extra = deepcopy(payload["candidate_blueprints"][0])
    extra.update(
        {
            "candidate_id": "H1C04",
            "method_variant": "method_4",
            "factor_variant": "factor_4",
            "archive_descriptors": {
                "mechanism_family": "mechanism_1",
                "turnover_bucket": "very_high",
                "beta_bucket": "market",
            },
        }
    )
    payload["candidate_blueprints"].append(extra)
    payload["branch_quotas"][0]["max_candidates"] = 4
    payload["exposure_budgets"] = {
        "candidate_budget": 19,
        "cumulative_trial_exposure_budget": 57,
        "prior_effective_trial_count": 8147,
    }
    payload["expensive_resource_rungs"][0]["input_candidate_limit"] = 19
    return payload


def _write_promotion_evidence(
    path: Path,
    payload: dict[str, Any],
    *,
    include_final: bool = True,
    observation_count: int = 1040,
) -> None:
    campaign_dir = path.parent
    artifact_dir = campaign_dir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    repository_root = path.parents[4]
    candidate_ids = [row["candidate_id"] for row in payload["candidate_blueprints"]]
    cohort_ids = ["H1C01", "H2C01"]
    blueprints = {row["candidate_id"]: row for row in payload["candidate_blueprints"]}
    contract = ResearchCampaignContract.model_validate(payload)
    contract_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    partition_path = artifact_dir / "development-partition-contract.json"
    partition_path.write_text(
        json.dumps({"partition_id": "development_validation", "kind": "development"}),
        encoding="utf-8",
    )
    partition_ref = partition_path.relative_to(repository_root).as_posix()
    partition_sha256 = hashlib.sha256(partition_path.read_bytes()).hexdigest()
    qd_candidates = []
    for index, candidate_id in enumerate(candidate_ids):
        metrics_path = artifact_dir / f"metrics-{candidate_id}.json"
        metrics_path.write_text(
            json.dumps({"candidate_id": candidate_id, "quality": 2.0 - index / 100.0}),
            encoding="utf-8",
        )
        qd_candidates.append(
            QualityDiversityCandidate(
                candidate_id=candidate_id,
                hypothesis_id=blueprints[candidate_id]["hypothesis_id"],
                branch=blueprints[candidate_id]["branch_id"],
                archive_descriptors=blueprints[candidate_id]["archive_descriptors"],
                quality=2.0 - index / 100.0,
                quality_metric=payload["qd_archive"]["quality_metric"],
                visibility_partition="development_validation",
                metrics_snapshot_path=metrics_path.relative_to(repository_root).as_posix(),
                metrics_snapshot_sha256=hashlib.sha256(metrics_path.read_bytes()).hexdigest(),
                partition_contract_path=partition_ref,
                partition_contract_sha256=partition_sha256,
                promotion_eligible=blueprints[candidate_id]["promotion_eligible"],
                resource_rung=0,
            )
        )
    archive = build_quality_diversity_archive(
        qd_candidates,
        quality_diversity_policy_from_campaign(
            contract,
            campaign_contract_sha256=contract_sha256,
        ),
        require_complete_inventory=True,
    )
    archive_path = campaign_dir / "qd-archive.json"
    archive_path.write_text(json.dumps(archive.model_dump()), encoding="utf-8")

    ledger = initialize_allocation_ledger(
        contract,
        campaign_contract_sha256=contract_sha256,
    )
    for candidate_id in candidate_ids:
        ledger = append_allocation_entry(
            ledger,
            candidate_id=candidate_id,
            decision="advance" if candidate_id in cohort_ids else "reject",
            resource_used={"candidate_evaluations": 1.0},
            metrics_snapshot_sha256=hashlib.sha256(candidate_id.encode()).hexdigest(),
            effective_trial_exposure=1.0,
            visibility_partition="development_validation",
        )
    ledger_path = campaign_dir / "allocation-ledger.jsonl"
    ledger_path.write_text(
        "".join(json.dumps(item.model_dump()) + "\n" for item in ledger.entries),
        encoding="utf-8",
    )

    cohort_payload = {
        "schema_version": 1,
        "campaign_id": payload["campaign_id"],
        "candidate_ids": cohort_ids,
        "selection_partition_id": "development_validation",
        "selected_before_frozen_oos": True,
        "qd_archive_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        "allocation_ledger_head_sha256": ledger.head_sha256,
    }
    (artifact_dir / "promotion-cohort.json").write_text(
        json.dumps(cohort_payload), encoding="utf-8"
    )
    cohort_path = artifact_dir / "promotion-cohort.json"
    # Family-scoped: excludes ``prior_effective_trial_count`` from the
    # DSR/PBO/SPA trial count (see campaign.py Work Item A1); the seal's
    # incremental figure is therefore just the family count itself.
    effective_trial_count = family_effective_trial_count_from_ledger(contract, ledger)
    prior_effective_trial_count = contract.exposure_budgets.prior_effective_trial_count
    seal_payload = {
        "schema_version": 1,
        "campaign_id": payload["campaign_id"],
        "campaign_contract_sha256": contract_sha256,
        "promotion_cohort_sha256": hashlib.sha256(cohort_path.read_bytes()).hexdigest(),
        "qd_archive_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        "allocation_ledger_head_sha256": ledger.head_sha256,
        "candidate_inventory_sha256": ledger.candidate_inventory_sha256,
        "effective_trial_count": effective_trial_count,
        "frozen_oos_read_at_seal": False,
        "prior_effective_trial_count": prior_effective_trial_count,
        "incremental_effective_trial_count": effective_trial_count,
    }
    seal_path = artifact_dir / "pre-oos-seal.json"
    seal_path.write_text(json.dumps(seal_payload), encoding="utf-8")
    if not include_final:
        return

    seal_sha256 = hashlib.sha256(seal_path.read_bytes()).hexdigest()
    dates = [
        (date(2024, 1, 1) + timedelta(days=index)).isoformat() for index in range(observation_count)
    ]
    benchmark_returns = [0.0001 + 0.00003 * ((index % 7) - 3) for index in range(observation_count)]
    tqqq_returns = [
        0.0015 + 0.006 * (((index * 7) % 19) - 9) / 9.0 for index in range(observation_count)
    ]
    candidate_returns = {
        "H1C01": [
            0.90 * tqqq_returns[index] + 0.0009 + 0.0002 * (((index * 17) % 11) - 5) / 5.0
            for index in range(observation_count)
        ],
        "H2C01": [
            0.86 * tqqq_returns[index] + 0.0010 + 0.0002 * (((index * 11 + 3) % 13) - 6) / 6.0
            for index in range(observation_count)
        ],
    }
    matrix_path = artifact_dir / "common-return-matrix.json"
    matrix_payload = {
        "schema_version": 1,
        "campaign_id": payload["campaign_id"],
        "partition_id": "frozen_oos",
        "candidate_ids": cohort_ids,
        "pre_oos_seal_sha256": seal_sha256,
        "return_stream_identity": {
            "frequency": "daily",
            "primary_cost_bps": 20,
            "benchmark": "BIL",
            "continuous_across_folds": True,
            "terminal_liquidation_included": False,
        },
        "dates": dates,
        "benchmark_returns": benchmark_returns,
        "returns": candidate_returns,
    }
    matrix_path.write_text(json.dumps(matrix_payload), encoding="utf-8")
    policy = payload["statistical_family_policy"]
    stats = recompute_campaign_statistics(
        candidate_ids=cohort_ids,
        candidate_returns=candidate_returns,
        benchmark_returns=benchmark_returns,
        effective_trial_count=effective_trial_count,
        dsr_hac_lag=policy["dsr_hac_lag"],
        pbo_block_count=policy["pbo_block_count"],
        pbo_in_sample_block_count=policy["pbo_in_sample_block_count"],
        spa_block_length=policy["spa_block_length"],
        spa_resample_count=policy["spa_resample_count"],
        spa_seed=policy["spa_seed"],
    )
    dsr_pass = stats.dsr_probability >= policy["dsr_minimum"]
    pbo_pass = stats.pbo_probability <= policy["pbo_maximum"]
    spa_pass = stats.spa_p_value <= policy["spa_p_value_maximum"]
    sharpe_pass = all(
        value > policy["primary_sharpe_minimum"]
        for value in stats.candidate_sharpe_excess_bil.values()
    )
    (artifact_dir / "statistical-family-gates.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "campaign_id": payload["campaign_id"],
                "candidate_ids": cohort_ids,
                "pre_oos_seal_sha256": seal_sha256,
                "common_return_matrix_sha256": hashlib.sha256(matrix_path.read_bytes()).hexdigest(),
                "effective_trial_count": effective_trial_count,
                "all_candidate_sharpe_values_defined": True,
                "candidate_sharpe_excess_bil": stats.candidate_sharpe_excess_bil,
                "dsr": {
                    "value": stats.dsr_probability,
                    "threshold": policy["dsr_minimum"],
                    "operator": ">=",
                    "passed": dsr_pass,
                },
                "pbo": {
                    "value": stats.pbo_probability,
                    "threshold": policy["pbo_maximum"],
                    "operator": "<=",
                    "passed": pbo_pass,
                },
                "spa": {
                    "value": stats.spa_p_value,
                    "threshold": policy["spa_p_value_maximum"],
                    "operator": "<=",
                    "passed": spa_pass,
                },
                "family_gate_pass": (
                    len(dates) >= MIN_DSR_STREAM_ROWS
                    and (
                        sharpe_pass and dsr_pass
                        if policy.get("promotion_stage") == "paper_entry"
                        else sharpe_pass and dsr_pass and pbo_pass and spa_pass
                    )
                ),
            }
        ),
        encoding="utf-8",
    )

    promotion_policy = payload["candidate_promotion_policy"]
    benchmark_streams = {
        "BIL": benchmark_returns,
        "SPY": [0.40 * value for value in tqqq_returns],
        "QQQ": [0.50 * value for value in tqqq_returns],
        "XLK": [0.60 * value for value in tqqq_returns],
        "TQQQ": tqqq_returns,
    }
    benchmark_roles = {}
    stress_returns = {}
    development_fold_returns = {}
    metrics = {}
    for candidate_id in cohort_ids:
        same_symbol_id = f"{candidate_id}_same_symbol"
        equal_weight_id = f"{candidate_id}_equal_weight"
        ex_post_best_id = f"{candidate_id}_ex_post_best"
        benchmark_streams[same_symbol_id] = [0.48 * value for value in tqqq_returns]
        benchmark_streams[equal_weight_id] = [0.44 * value for value in tqqq_returns]
        benchmark_streams[ex_post_best_id] = [0.70 * value for value in tqqq_returns]
        benchmark_roles[candidate_id] = {
            "same_symbol_buy_and_hold": same_symbol_id,
            "equal_weight_universe": equal_weight_id,
            "market_proxy": "SPY",
            "growth_proxy": "QQQ",
            "sector_theme_proxy": "XLK",
            "cash_proxy": "BIL",
            "leveraged_growth_proxy": "TQQQ",
            "ex_post_best_symbol": ex_post_best_id,
        }
        stress_returns[candidate_id] = [value - 0.0002 for value in candidate_returns[candidate_id]]
        development_fold_returns[candidate_id] = [
            candidate_returns[candidate_id][offset : offset + 32] for offset in range(0, 128, 32)
        ]
        recomputed = recompute_candidate_promotion_metrics(
            candidate_returns=candidate_returns[candidate_id],
            qqq_returns=benchmark_streams["QQQ"],
            tqqq_returns=benchmark_streams["TQQQ"],
            stress_returns=stress_returns[candidate_id],
            development_fold_returns=development_fold_returns[candidate_id],
            annualization_sessions=promotion_policy["annualization_sessions"],
        )
        if abs(recomputed["qqq_correlation"]) <= QQQ_ORTHOGONALITY_CORRELATION_THRESHOLD:
            qqq_capture_ratio_pass = True
            qqq_downside_capture_pass = True
        else:
            qqq_capture_ratio_pass = (
                recomputed["qqq_capture_ratio"] >= promotion_policy["qqq_capture_ratio_minimum"]
            )
            qqq_downside_capture_pass = (
                recomputed["qqq_downside_capture"]
                <= promotion_policy["qqq_downside_capture_maximum"]
            )
        passed_gates = {
            "cagr_excess_qqq": (
                recomputed["cagr_excess_qqq"] >= promotion_policy["cagr_excess_qqq_minimum"]
            ),
            "qqq_capture_ratio": qqq_capture_ratio_pass,
            "qqq_downside_capture": qqq_downside_capture_pass,
            "max_drawdown": (
                recomputed["max_drawdown"] >= promotion_policy["max_drawdown_minimum"]
            ),
            "mar": recomputed["mar"] >= promotion_policy["mar_minimum"],
            "positive_fold_count": (
                recomputed["positive_fold_count"] >= promotion_policy["minimum_positive_folds"]
            ),
            "stress_total_return": (
                recomputed["stress_total_return"] > promotion_policy["stress_total_return_minimum"]
            ),
        }
        metrics[candidate_id] = {
            **recomputed,
            "passed_gates": passed_gates,
            "all_gates_pass": all(passed_gates.values()),
        }
    (artifact_dir / "candidate-promotion-gates.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "campaign_id": payload["campaign_id"],
                "candidate_ids": cohort_ids,
                "pre_oos_seal_sha256": seal_sha256,
                "common_return_matrix_sha256": hashlib.sha256(matrix_path.read_bytes()).hexdigest(),
                "dates": dates,
                "primary_return_stream_identity": matrix_payload["return_stream_identity"],
                "stress_return_stream_identity": {
                    **matrix_payload["return_stream_identity"],
                    "primary_cost_bps": promotion_policy["stress_cost_bps"],
                },
                "development_partition_id": promotion_policy["development_partition_id"],
                "development_fold_ids": promotion_policy["development_fold_ids"],
                "benchmark_returns": benchmark_streams,
                "benchmark_roles": benchmark_roles,
                "stress_returns": stress_returns,
                "development_fold_returns": development_fold_returns,
                "metrics": metrics,
                "all_candidates_pass": all(row["all_gates_pass"] for row in metrics.values()),
            }
        ),
        encoding="utf-8",
    )


def test_campaign_contract_path_load_and_validate_six_branch_campaign(tmp_path: Path) -> None:
    payload = _passing_contract()
    path = campaign_contract_path(payload["campaign_id"], tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    _write_promotion_evidence(path, payload, include_final=False)

    assert path.name == CAMPAIGN_FILENAME
    loaded = load_campaign_contract(payload["campaign_id"], tmp_path)
    assert isinstance(loaded, ResearchCampaignContract)
    assert loaded.campaign_id == "momentum_qd_r1"

    report = validate_campaign_contract(payload["campaign_id"], tmp_path, stage="pre-oos")

    assert report.status == "ok"
    assert report.blocked == []
    assert report.counts.hypotheses == 7
    assert report.counts.branches == 6
    assert report.counts.preregistered_candidates == 18
    assert report.counts.candidate_budget == 18
    assert report.counts.branch_minimum_candidates == 12
    assert report.counts.branch_maximum_candidates == 18
    assert report.counts.control_hypotheses == 1
    assert report.to_dict()["counts"]["cumulative_trial_exposure_budget"] == 54
    assert not (path.parent / "artifacts/common-return-matrix.json").exists()
    assert not (path.parent / "artifacts/statistical-family-gates.json").exists()


def test_campaign_contract_locks_advancing_pair_correlation_identity() -> None:
    contract = ResearchCampaignContract.model_validate(_passing_contract())

    assert contract.statistical_family_policy.advancing_pair_correlation.model_dump() == {
        "method": "pearson",
        "return_stream": "development_validation_continuous_daily_primary_20bps_terminal_free",
        "absolute_maximum": 0.70,
        "operator": "<=",
        "minimum_passing_pair_count": 1,
    }


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("method", "spearman"),
        ("return_stream", "frozen_oos_continuous_daily_primary_20bps_terminal_free"),
        ("absolute_maximum", -0.01),
        ("absolute_maximum", 1.01),
        ("operator", "<"),
        ("minimum_passing_pair_count", 0),
    ],
    ids=[
        "wrong_method",
        "wrong_return_stream",
        "threshold_below_zero",
        "threshold_above_one",
        "wrong_operator",
        "zero_required_pairs",
    ],
)
def test_campaign_contract_rejects_invalid_advancing_pair_correlation_policy(
    field: str,
    invalid_value: Any,
) -> None:
    payload = _passing_contract()
    payload["statistical_family_policy"]["advancing_pair_correlation"][field] = invalid_value

    with pytest.raises(ValidationError) as exc_info:
        ResearchCampaignContract.model_validate(payload)

    assert any(
        error["loc"] == ("statistical_family_policy", "advancing_pair_correlation", field)
        for error in exc_info.value.errors()
    )


def test_campaign_trial_accounting_adds_prior_only_after_incremental_floor() -> None:
    payload = _passing_contract()
    payload["exposure_budgets"]["prior_effective_trial_count"] = 8147
    contract = ResearchCampaignContract.model_validate(payload)
    ledger = initialize_allocation_ledger(
        contract,
        campaign_contract_sha256="f" * 64,
    )

    assert ledger.effective_trial_exposure_budget == 54
    assert effective_trial_count_from_ledger(contract, ledger) == 8147 + 18

    fully_exposed = append_allocation_entry(
        ledger,
        candidate_id="H1C01",
        decision="allocate",
        resource_used={"candidate_evaluations": 54.0},
        metrics_snapshot_sha256="a" * 64,
        effective_trial_exposure=54.0,
        visibility_partition="development_train",
    )

    assert effective_trial_count_from_ledger(contract, fully_exposed) == 8147 + 54


@pytest.mark.parametrize(
    ("exposures", "expected_effective_trial_count"),
    [
        ([1.0] * 19, 8166),
        ([1.0] * 16 + [0.0] * 3, 8166),
        ([19.01], 8167),
        ([57.0], 8204),
    ],
    ids=[
        "nineteen_unit_exposures",
        "three_dependency_skips_keep_candidate_floor",
        "fractional_exposure_rounds_up",
        "full_incremental_budget",
    ],
)
def test_campaign_trial_accounting_uses_candidate_floor_and_ceiling(
    exposures: list[float], expected_effective_trial_count: int
) -> None:
    contract = ResearchCampaignContract.model_validate(_nineteen_candidate_contract())
    ledger = initialize_allocation_ledger(
        contract,
        campaign_contract_sha256="f" * 64,
    )
    candidate_ids = [row.candidate_id for row in contract.candidate_blueprints]
    for candidate_id, exposure in zip(candidate_ids[: len(exposures)], exposures, strict=True):
        ledger = append_allocation_entry(
            ledger,
            candidate_id=candidate_id,
            decision="dependency_skipped" if exposure == 0.0 else "advance",
            resource_used={"candidate_evaluations": exposure},
            metrics_snapshot_sha256=hashlib.sha256(candidate_id.encode()).hexdigest(),
            effective_trial_exposure=exposure,
            visibility_partition="development_validation",
        )

    assert effective_trial_count_from_ledger(contract, ledger) == expected_effective_trial_count


def test_campaign_trial_accounting_rejects_fraction_above_incremental_budget() -> None:
    contract = ResearchCampaignContract.model_validate(_nineteen_candidate_contract())
    ledger = initialize_allocation_ledger(
        contract,
        campaign_contract_sha256="f" * 64,
    )

    with pytest.raises(ValueError, match="trial exposure budget exceeded"):
        append_allocation_entry(
            ledger,
            candidate_id=contract.candidate_blueprints[0].candidate_id,
            decision="advance",
            resource_used={"candidate_evaluations": 57.01},
            metrics_snapshot_sha256="a" * 64,
            effective_trial_exposure=57.01,
            visibility_partition="development_validation",
        )


def test_mom_breadth_generator_has_one_four_way_trial_accounting_identity(
    tmp_path: Path,
) -> None:
    campaign = _nineteen_candidate_contract()
    campaign_path = tmp_path / MOM_BREADTH_CAMPAIGN_PATH
    campaign_path.parent.mkdir(parents=True)
    campaign_path.write_text(json.dumps(campaign), encoding="utf-8")
    iter_id = "mom_breadth_crossasset_trend_r1"
    candidate_ids = ["TSM01"]
    search_candidates = [
        {
            "candidate_id": "TSM01",
            "method_variant": "absolute_trend",
            "factor_variant": "trend_126",
        }
    ]
    specs = {
        "TSM01": {
            "path": Path("strategy_specs/drafts/tsm01.yaml"),
            "hash": "a" * 64,
        }
    }
    expected = _trial_accounting_identity(campaign)
    validation = _validation_contract(campaign, iter_id, candidate_ids)
    cumulative = _cumulative_trial_contract(campaign, iter_id, candidate_ids)
    search = _search_space(
        campaign=campaign,
        iter_id=iter_id,
        branch={
            "strategy_stem": "test_trend",
            "objective": "test",
            "path": "cross_asset_time_series_trend",
            "hypothesis_id": "H2_CROSSASSET_TREND",
        },
        candidates=search_candidates,
        specs=specs,
        root=tmp_path,
        finalized=False,
    )
    manifest = _candidate_manifest_payload(
        campaign=campaign,
        iter_id=iter_id,
        candidates=[
            {
                "candidate_id": "TSM01",
                "spec_path": specs["TSM01"]["path"].as_posix(),
            }
        ],
        specs=specs,
        contracts={},
    )

    views = [
        {key: validation["dsr"][key] for key in TRIAL_ACCOUNTING_IDENTITY_KEYS},
        {key: cumulative[key] for key in TRIAL_ACCOUNTING_IDENTITY_KEYS},
        search["trial_accounting"],
        manifest["trial_accounting"],
    ]
    assert views == [expected] * 4
    assert expected == {
        "prior_effective_trial_count": 8147,
        "campaign_candidate_count": 19,
        "minimum_incremental_trial_count": 19,
        "campaign_trial_exposure_budget": 57,
        "minimum_effective_trial_count": 8166,
        "maximum_effective_trial_count": 8204,
        "effective_trial_count_source": "campaign_pre_oos_seal",
    }


def test_pre_oos_seal_trial_identity_is_family_scoped_not_prior_inclusive(
    tmp_path: Path,
) -> None:
    payload = _passing_contract()
    payload["exposure_budgets"]["prior_effective_trial_count"] = 8147
    path = campaign_contract_path(payload["campaign_id"], tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    _write_promotion_evidence(path, payload, include_final=False)

    assert validate_campaign_contract(path, tmp_path, stage="pre-oos").status == "ok"
    seal_path = path.parent / "artifacts/pre-oos-seal.json"
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    # ``prior_effective_trial_count`` is carried on the seal purely as a
    # lifetime diagnostic; it must not be added into the DSR/PBO/SPA trial
    # count, so ``effective_trial_count`` and ``incremental_effective_trial_
    # count`` both equal this family's own 18 candidate trials, not 8147+18.
    assert seal["prior_effective_trial_count"] == 8147
    assert seal["incremental_effective_trial_count"] == 18
    assert seal["effective_trial_count"] == 18

    seal["effective_trial_count"] = payload["exposure_budgets"]["cumulative_trial_exposure_budget"]
    seal_path.write_text(json.dumps(seal), encoding="utf-8")
    report = validate_campaign_contract(path, tmp_path, stage="pre-oos")

    assert "pre_oos_seal_effective_trial_count_mismatch:54:18" in report.blocked


@pytest.mark.parametrize(
    ("effective_trial_count", "expected_prefix"),
    [
        (17, "statistical_family_gates_trial_count_below_candidate_budget:17:18"),
        (33, "statistical_family_gates_trial_count_above_exposure_budget:33:32"),
    ],
)
def test_final_trial_gate_bounds_are_family_scoped_not_prior_inclusive(
    tmp_path: Path,
    effective_trial_count: int,
    expected_prefix: str,
) -> None:
    payload = _passing_contract()
    payload["exposure_budgets"]["prior_effective_trial_count"] = 8147
    path = campaign_contract_path(payload["campaign_id"], tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    _write_promotion_evidence(path, payload)
    gates_path = path.parent / "artifacts/statistical-family-gates.json"
    gates = json.loads(gates_path.read_text(encoding="utf-8"))
    gates["effective_trial_count"] = effective_trial_count
    gates_path.write_text(json.dumps(gates), encoding="utf-8")

    report = validate_campaign_contract(path, tmp_path, stage="final")

    assert expected_prefix in report.blocked


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            lambda payload: (
                payload["hypotheses"][1].update({"parent_hypothesis_id": "H2"})
                or payload["hypotheses"][2].update({"parent_hypothesis_id": "H1"})
            ),
            "hypothesis_cycle:H1,H2",
        ),
        (
            lambda payload: payload["hypotheses"][1].update({"parent_hypothesis_id": "UNKNOWN"}),
            "hypothesis_parent_missing:H1:UNKNOWN",
        ),
    ],
)
def test_campaign_rejects_cycle_or_disconnected_parent(
    mutation: Any,
    expected: str,
) -> None:
    payload = _passing_contract()
    mutation(payload)

    report = validate_campaign_contract(payload)

    assert report.status == "blocked"
    assert expected in report.blocked
    assert any(item.startswith("hypothesis_tree_disconnected:") for item in report.blocked)


def test_campaign_rejects_branch_minimum_quota_overflow() -> None:
    payload = _passing_contract()
    payload["exposure_budgets"]["candidate_budget"] = 11

    report = validate_campaign_contract(payload)

    assert report.status == "blocked"
    assert "branch_minimum_quota_overflow:12>11" in report.blocked


def test_campaign_rejects_candidate_inventory_over_branch_and_global_budget() -> None:
    payload = _passing_contract()
    extra = deepcopy(payload["candidate_blueprints"][0])
    extra["candidate_id"] = "H1C04"
    payload["candidate_blueprints"].append(extra)

    report = validate_campaign_contract(payload)

    assert "campaign_candidate_inventory_budget_mismatch:19:18" in report.blocked
    assert "campaign_branch_candidate_count_above_max:B1:4>3" in report.blocked


def test_campaign_rejects_static_control_candidate_promotion() -> None:
    payload = _passing_contract()
    payload["candidate_blueprints"][-1]["promotion_eligible"] = True

    report = validate_campaign_contract(payload)

    assert "campaign_candidate_promotion_exceeds_hypothesis:H6C03" in report.blocked
    assert "campaign_control_candidate_promotion_eligible:H6C03" in report.blocked


@pytest.mark.parametrize(
    "operation", ["candidate_generation", "candidate_pruning", "model_training"]
)
def test_campaign_rejects_frozen_oos_visible_to_exploration(operation: str) -> None:
    payload = _passing_contract()
    payload["visibility_partitions"][2]["allowed_operations"].append(operation)

    report = validate_campaign_contract(payload)

    assert report.status == "blocked"
    assert any(
        item.startswith("protected_partition_exposed_to_exploration:frozen_oos:")
        for item in report.blocked
    )


def test_campaign_rejects_expensive_rung_reading_oos() -> None:
    payload = _passing_contract()
    payload["expensive_resource_rungs"][0]["read_partition_ids"].append("frozen_oos")

    report = validate_campaign_contract(payload)

    assert report.status == "blocked"
    assert (
        "resource_rung_reads_non_development_partition:ML1:frozen_oos:frozen_oos" in report.blocked
    )


def test_campaign_rejects_noncanonical_identity_and_unbudgeted_leaf() -> None:
    payload = _passing_contract()
    payload["campaign_id"] = "Momentum.QD.R1"
    payload["branch_quotas"].pop()

    report = validate_campaign_contract(payload)

    assert "campaign_id_invalid:Momentum.QD.R1" in report.blocked
    assert "leaf_hypotheses_without_branch_quota:H6" in report.blocked


def test_campaign_rejects_archive_partition_without_archive_authority() -> None:
    payload = _passing_contract()
    payload["visibility_partitions"][1]["allowed_operations"].remove("archive_update")

    report = validate_campaign_contract(payload)

    assert (
        "archive_quality_partition_disallows_archive_update:development_validation"
        in report.blocked
    )


def test_static_hotspot_is_allowed_only_as_non_promotable_control() -> None:
    passing = validate_campaign_contract(_passing_contract())
    assert passing.status == "ok"

    payload = _passing_contract()
    payload["hypotheses"][-1]["promotion_eligible"] = True

    report = validate_campaign_contract(payload)

    assert report.status == "blocked"
    assert "static_hotspot_cannot_be_promotion_eligible:H6" in report.blocked


@pytest.mark.parametrize(
    "descriptor",
    [
        "economic_mechanism",
        "universe_or_asset_class",
        "horizon",
        "data_modality",
        "portfolio_construction",
        "execution_style",
    ],
)
def test_campaign_rejects_missing_or_empty_hypothesis_descriptor(descriptor: str) -> None:
    payload = _passing_contract()
    payload["hypotheses"][1][descriptor] = "   "

    report = validate_campaign_contract(payload)

    assert report.status == "blocked"
    assert any(
        item.startswith(f"contract_schema_invalid:hypotheses.1.{descriptor}:")
        for item in report.blocked
    )


@pytest.mark.parametrize(
    "tie_break_rules",
    [
        [],
        [
            {"field": "random", "direction": "ascending"},
            {"field": "candidate_id", "direction": "ascending"},
        ],
        [{"field": "max_drawdown", "direction": "ascending"}],
    ],
)
def test_campaign_rejects_empty_or_nondeterministic_archive_tie_break(
    tie_break_rules: list[dict[str, str]],
) -> None:
    payload = _passing_contract()
    payload["qd_archive"]["tie_break_rules"] = tie_break_rules

    report = validate_campaign_contract(payload)

    assert report.status == "blocked"
    assert any(
        "tie_break" in item or "contract_schema_invalid:qd_archive.tie_break_rules" in item
        for item in report.blocked
    )


def test_campaign_rejects_unsupported_multiple_elites_per_cell() -> None:
    payload = _passing_contract()
    payload["qd_archive"]["max_elites_per_cell"] = 2

    report = validate_campaign_contract(payload)

    assert "archive_max_elites_per_cell_not_supported_by_deterministic_qd_v1" in report.blocked


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("generation_mode", "unrestricted_code_generation"),
        ("mutation_mode", "unrestricted_mutation"),
    ],
)
def test_campaign_rejects_unrestricted_generation_or_mutation(
    field: str,
    value: str,
) -> None:
    payload = _passing_contract()
    payload["exploration_policy"][field] = value

    report = validate_campaign_contract(payload)

    assert report.status == "blocked"
    assert f"unrestricted_generation_or_mutation_mode:{value}" in report.blocked


def test_pre_oos_and_final_require_statistical_promotion_references() -> None:
    payload = _passing_contract()
    payload["promotion_evidence"] = None

    assert validate_campaign_contract(payload, stage="pre-discovery").status == "ok"
    for stage in ("pre-oos", "final"):
        report = validate_campaign_contract(payload, stage=stage)
        assert report.status == "blocked"
        assert "promotion_evidence_references_missing" in report.blocked


def test_pre_oos_validation_rejects_missing_declared_evidence_paths(tmp_path: Path) -> None:
    payload = deepcopy(_passing_contract())
    payload["promotion_evidence"] = {
        "promotion_cohort_ref": "artifacts/missing-cohort.json",
        "pre_oos_seal_ref": "artifacts/missing-seal.json",
        "common_return_matrix_ref": "artifacts/missing-returns.json",
        "statistical_family_gate_ref": "artifacts/missing-gates.json",
        "candidate_promotion_gate_ref": "artifacts/missing-candidate-gates.json",
    }

    report = validate_campaign_contract(payload, stage="final")

    assert report.status == "blocked"
    assert "promotion_cohort_missing" in report.blocked


def test_final_requires_oos_evidence_after_pre_oos_seal_passes(tmp_path: Path) -> None:
    payload = _passing_contract()
    path = campaign_contract_path(payload["campaign_id"], tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    _write_promotion_evidence(path, payload, include_final=False)

    assert validate_campaign_contract(path, tmp_path, stage="pre-oos").status == "ok"
    report = validate_campaign_contract(path, tmp_path, stage="final")

    assert "common_return_matrix_missing" in report.blocked
    assert "statistical_family_gates_missing" in report.blocked
    assert "candidate_promotion_gates_missing" in report.blocked


def test_final_validation_rejects_tampered_common_return_matrix(tmp_path: Path) -> None:
    payload = _passing_contract()
    path = campaign_contract_path(payload["campaign_id"], tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    _write_promotion_evidence(path, payload)
    matrix_path = path.parent / "artifacts/common-return-matrix.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    matrix["returns"]["H1C01"][0] = 9.0
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")

    report = validate_campaign_contract(path, tmp_path, stage="final")

    assert report.status == "blocked"
    assert "statistical_family_gates_common_return_matrix_sha256_mismatch" in report.blocked


def test_final_validation_enforces_strict_primary_sharpe_gate(tmp_path: Path) -> None:
    payload = _passing_contract()
    path = campaign_contract_path(payload["campaign_id"], tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    _write_promotion_evidence(path, payload)
    gates_path = path.parent / "artifacts/statistical-family-gates.json"
    gates = json.loads(gates_path.read_text(encoding="utf-8"))
    gates["candidate_sharpe_excess_bil"]["H1C01"] = 1.0
    gates_path.write_text(json.dumps(gates), encoding="utf-8")

    report = validate_campaign_contract(path, tmp_path, stage="final")

    assert "statistical_family_primary_sharpe_gate_failed:H1C01" in report.blocked


@pytest.mark.parametrize(
    ("promotion_stage", "expect_family_gate_failed"),
    [("live_entry", True), ("paper_entry", False)],
)
def test_paper_entry_stage_demotes_pbo_and_spa_to_diagnostics(
    tmp_path: Path,
    promotion_stage: str,
    expect_family_gate_failed: bool,
) -> None:
    payload = _passing_contract()
    # Make PBO/SPA fail on any real computed value; DSR and Sharpe stay
    # satisfiable so this isolates A6's stage-conditional PBO/SPA gating.
    payload["statistical_family_policy"]["pbo_maximum"] = 0.0
    payload["statistical_family_policy"]["spa_p_value_maximum"] = 1e-9
    payload["statistical_family_policy"]["promotion_stage"] = promotion_stage
    path = campaign_contract_path(payload["campaign_id"], tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    _write_promotion_evidence(path, payload)

    report = validate_campaign_contract(path, tmp_path, stage="final")

    assert ("statistical_family_gate_failed" in report.blocked) is expect_family_gate_failed
    assert "statistical_family_gate_family_pass_flag_inconsistent" not in report.blocked


def test_final_blocks_dsr_below_the_minimum_stitched_oos_row_count(tmp_path: Path) -> None:
    payload = _passing_contract()
    path = campaign_contract_path(payload["campaign_id"], tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    short_count = MIN_DSR_STREAM_ROWS - 1
    _write_promotion_evidence(path, payload, observation_count=short_count)

    report = validate_campaign_contract(path, tmp_path, stage="final")

    assert (
        f"statistical_family_gates_stitched_stream_too_short:{short_count}:{MIN_DSR_STREAM_ROWS}"
        in report.blocked
    )
    assert "statistical_family_gate_family_pass_flag_inconsistent" not in report.blocked


def test_final_recomputes_candidate_promotion_metrics(tmp_path: Path) -> None:
    payload = _passing_contract()
    path = campaign_contract_path(payload["campaign_id"], tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    _write_promotion_evidence(path, payload)
    gates_path = path.parent / "artifacts/candidate-promotion-gates.json"
    gates = json.loads(gates_path.read_text(encoding="utf-8"))
    gates["metrics"]["H1C01"]["cagr"] = 99.0
    gates_path.write_text(json.dumps(gates), encoding="utf-8")

    report = validate_campaign_contract(path, tmp_path, stage="final")

    assert "candidate_promotion_gates_metric_recomputation_mismatch:H1C01:cagr" in report.blocked


@pytest.mark.parametrize(
    ("policy_field", "threshold", "gate_name"),
    [
        ("cagr_excess_qqq_minimum", 10.0, "cagr_excess_qqq"),
        ("qqq_capture_ratio_minimum", 1000.0, "qqq_capture_ratio"),
        ("qqq_downside_capture_maximum", -1000.0, "qqq_downside_capture"),
        ("max_drawdown_minimum", 0.0, "max_drawdown"),
        ("mar_minimum", 1000.0, "mar"),
    ],
)
def test_final_enforces_each_candidate_performance_gate(
    tmp_path: Path,
    policy_field: str,
    threshold: float,
    gate_name: str,
) -> None:
    payload = _passing_contract()
    payload["candidate_promotion_policy"][policy_field] = threshold
    path = campaign_contract_path(payload["campaign_id"], tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    _write_promotion_evidence(path, payload)

    report = validate_campaign_contract(path, tmp_path, stage="final")

    assert f"candidate_promotion_gates_failed:H1C01:{gate_name}" in report.blocked


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            lambda gates: gates["primary_return_stream_identity"].update({"primary_cost_bps": 10}),
            "candidate_promotion_gates_primary_return_stream_identity_mismatch",
        ),
        (
            lambda gates: gates["stress_return_stream_identity"].update({"primary_cost_bps": 20}),
            "candidate_promotion_gates_stress_return_stream_identity_mismatch",
        ),
        (
            lambda gates: gates.update({"development_fold_ids": ["D1", "D2", "D4", "D3"]}),
            "candidate_promotion_gates_development_fold_identity_mismatch",
        ),
    ],
)
def test_final_rejects_candidate_return_stream_identity_drift(
    tmp_path: Path,
    mutation: Any,
    expected: str,
) -> None:
    payload = _passing_contract()
    path = campaign_contract_path(payload["campaign_id"], tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    _write_promotion_evidence(path, payload)
    gates_path = path.parent / "artifacts/candidate-promotion-gates.json"
    gates = json.loads(gates_path.read_text(encoding="utf-8"))
    mutation(gates)
    gates_path.write_text(json.dumps(gates), encoding="utf-8")

    report = validate_campaign_contract(path, tmp_path, stage="final")

    assert expected in report.blocked


@pytest.mark.parametrize(
    ("gate_name", "expected_fragment"),
    [
        ("stress_total_return", "candidate_promotion_gates_failed:H1C01:stress_total_return"),
        (
            "positive_fold_count",
            "candidate_promotion_gates_failed:H1C01:positive_fold_count",
        ),
    ],
)
def test_final_rejects_reconciled_candidate_gate_failures(
    tmp_path: Path,
    gate_name: str,
    expected_fragment: str,
) -> None:
    payload = _passing_contract()
    path = campaign_contract_path(payload["campaign_id"], tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    _write_promotion_evidence(path, payload)
    artifact_dir = path.parent / "artifacts"
    gates_path = artifact_dir / "candidate-promotion-gates.json"
    matrix = json.loads((artifact_dir / "common-return-matrix.json").read_text(encoding="utf-8"))
    gates = json.loads(gates_path.read_text(encoding="utf-8"))
    candidate_id = "H1C01"
    if gate_name == "stress_total_return":
        gates["stress_returns"][candidate_id] = [-0.001] * len(gates["dates"])
    else:
        gates["development_fold_returns"][candidate_id] = [
            [-0.01] * 5,
            [-0.01] * 5,
            [-0.01] * 5,
            [0.01] * 5,
        ]
    roles = gates["benchmark_roles"][candidate_id]
    recomputed = recompute_candidate_promotion_metrics(
        candidate_returns=matrix["returns"][candidate_id],
        qqq_returns=gates["benchmark_returns"][roles["growth_proxy"]],
        tqqq_returns=gates["benchmark_returns"][roles["leveraged_growth_proxy"]],
        stress_returns=gates["stress_returns"][candidate_id],
        development_fold_returns=gates["development_fold_returns"][candidate_id],
        annualization_sessions=payload["candidate_promotion_policy"]["annualization_sessions"],
    )
    row = gates["metrics"][candidate_id]
    row.update(recomputed)
    row["passed_gates"][gate_name] = False
    row["all_gates_pass"] = False
    gates["all_candidates_pass"] = False
    gates_path.write_text(json.dumps(gates), encoding="utf-8")

    report = validate_campaign_contract(path, tmp_path, stage="final")

    assert expected_fragment in report.blocked


def test_final_requires_complete_benchmark_role_evidence(tmp_path: Path) -> None:
    payload = _passing_contract()
    path = campaign_contract_path(payload["campaign_id"], tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    _write_promotion_evidence(path, payload)
    gates_path = path.parent / "artifacts/candidate-promotion-gates.json"
    gates = json.loads(gates_path.read_text(encoding="utf-8"))
    gates["benchmark_roles"]["H1C01"].pop("ex_post_best_symbol")
    gates_path.write_text(json.dumps(gates), encoding="utf-8")

    report = validate_campaign_contract(path, tmp_path, stage="final")

    assert "candidate_promotion_gates_benchmark_roles_mismatch:H1C01" in report.blocked


def test_final_recomputes_statistics_and_rejects_jointly_forged_losses(tmp_path: Path) -> None:
    payload = _passing_contract()
    path = campaign_contract_path(payload["campaign_id"], tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    _write_promotion_evidence(path, payload)
    matrix_path = path.parent / "artifacts/common-return-matrix.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    row_count = len(matrix["dates"])
    matrix["benchmark_returns"] = [0.0] * row_count
    matrix["returns"] = {
        candidate_id: [
            -0.50 + 0.01 * (((index * multiplier) % 17) - 8) / 8.0 for index in range(row_count)
        ]
        for candidate_id, multiplier in zip(matrix["candidate_ids"], (3, 5), strict=True)
    }
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
    gates_path = path.parent / "artifacts/statistical-family-gates.json"
    gates = json.loads(gates_path.read_text(encoding="utf-8"))
    gates["common_return_matrix_sha256"] = hashlib.sha256(matrix_path.read_bytes()).hexdigest()
    gates["candidate_sharpe_excess_bil"] = {
        candidate_id: 99.0 for candidate_id in matrix["candidate_ids"]
    }
    for name, value in (("dsr", 1.0), ("pbo", 0.0), ("spa", 0.0)):
        gates[name]["value"] = value
        gates[name]["passed"] = True
    gates["family_gate_pass"] = True
    gates_path.write_text(json.dumps(gates), encoding="utf-8")

    report = validate_campaign_contract(path, tmp_path, stage="final")

    assert report.status == "blocked"
    assert any(
        blocker.startswith("statistical_family_sharpe_recomputation_mismatch:")
        or blocker.startswith("statistical_family_recomputation_failed:")
        for blocker in report.blocked
    )


@pytest.mark.parametrize(
    ("mutation", "expected_fragment"),
    [
        (
            lambda archive: archive.update(
                {
                    "candidates": archive["candidates"][:2],
                    "eligible_candidate_count": 2,
                }
            ),
            "sealed inventory is incomplete",
        ),
        (
            lambda archive: archive["candidates"][0].update(
                {"visibility_partition": "development_forged_not_declared"}
            ),
            "selection visibility is outside explicit train/development partitions",
        ),
    ],
)
def test_pre_oos_rebuilds_qd_archive_and_rejects_forged_selection(
    tmp_path: Path,
    mutation: Any,
    expected_fragment: str,
) -> None:
    payload = _passing_contract()
    path = campaign_contract_path(payload["campaign_id"], tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    _write_promotion_evidence(path, payload, include_final=False)
    archive_path = path.parent / "qd-archive.json"
    archive = json.loads(archive_path.read_text(encoding="utf-8"))
    mutation(archive)
    archive_path.write_text(json.dumps(archive), encoding="utf-8")

    report = validate_campaign_contract(path, tmp_path, stage="pre-oos")

    assert report.status == "blocked"
    assert any(expected_fragment in blocker for blocker in report.blocked)


def test_pre_oos_rejects_rehashed_two_row_low_exposure_ledger(tmp_path: Path) -> None:
    payload = _passing_contract()
    path = campaign_contract_path(payload["campaign_id"], tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    _write_promotion_evidence(path, payload, include_final=False)
    contract = ResearchCampaignContract.model_validate(payload)
    ledger = initialize_allocation_ledger(
        contract,
        campaign_contract_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    for candidate_id in ("H1C01", "H2C01"):
        ledger = append_allocation_entry(
            ledger,
            candidate_id=candidate_id,
            decision="advance",
            resource_used={"candidate_evaluations": 0.01},
            metrics_snapshot_sha256=hashlib.sha256(candidate_id.encode()).hexdigest(),
            effective_trial_exposure=0.01,
            visibility_partition="development_validation",
        )
    ledger_path = path.parent / "allocation-ledger.jsonl"
    ledger_path.write_text(
        "".join(json.dumps(entry.model_dump()) + "\n" for entry in ledger.entries),
        encoding="utf-8",
    )
    cohort_path = path.parent / "artifacts/promotion-cohort.json"
    cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
    cohort["allocation_ledger_head_sha256"] = ledger.head_sha256
    cohort_path.write_text(json.dumps(cohort), encoding="utf-8")
    seal_path = path.parent / "artifacts/pre-oos-seal.json"
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    seal["allocation_ledger_head_sha256"] = ledger.head_sha256
    seal["promotion_cohort_sha256"] = hashlib.sha256(cohort_path.read_bytes()).hexdigest()
    seal_path.write_text(json.dumps(seal), encoding="utf-8")

    report = validate_campaign_contract(path, tmp_path, stage="pre-oos")

    assert report.status == "blocked"
    assert any(
        blocker.startswith("allocation_ledger_registered_candidates_missing:")
        for blocker in report.blocked
    )
    assert any(
        blocker.startswith("allocation_ledger_candidate_exposure_below_one:")
        for blocker in report.blocked
    )


def test_campaign_cli_validate_and_status_are_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _passing_contract()
    path = campaign_contract_path(payload["campaign_id"], tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr("open_composer.cli.project_root", lambda: tmp_path)
    runner = CliRunner()

    validated = runner.invoke(
        app,
        ["research", "campaign", "validate", payload["campaign_id"], "--json"],
        catch_exceptions=False,
    )
    status = runner.invoke(
        app,
        ["research", "campaign", "status", payload["campaign_id"], "--json"],
        catch_exceptions=False,
    )

    assert validated.exit_code == 0
    assert json.loads(validated.stdout)["status"] == "ok"
    status_payload = json.loads(status.stdout)
    assert status.exit_code == 0
    assert status_payload["phase"] == "pre_discovery_ready"
    assert status_payload["selection_visibility"] == "development_only"
    assert status_payload["selection_evidence_status"] == "not_materialized"
    assert status_payload["frozen_oos_influences_selection"] is False
    assert status_payload["stage_validations"]["pre-discovery"]["status"] == "ok"
    assert status_payload["stage_validations"]["pre-oos"]["status"] == "blocked"
    assert not (path.parent / "qd-archive.json").exists()
    assert not (path.parent / "allocation-ledger.jsonl").exists()


def test_campaign_cli_status_uses_stage_validation_for_materialized_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _passing_contract()
    path = campaign_contract_path(payload["campaign_id"], tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    _write_promotion_evidence(path, payload)
    monkeypatch.setattr("open_composer.cli.project_root", lambda: tmp_path)

    status = CliRunner().invoke(
        app,
        ["research", "campaign", "status", payload["campaign_id"], "--json"],
        catch_exceptions=False,
    )

    status_payload = json.loads(status.stdout)
    assert status.exit_code == 0
    assert status_payload["phase"] == "final_pass"
    assert status_payload["stage_validations"]["pre-oos"]["status"] == "ok"
    assert status_payload["stage_validations"]["final"]["status"] == "ok"
    assert status_payload["selection_evidence_status"] == "validated_development_only"
    assert status_payload["frozen_oos_influences_selection"] is False
    assert status_payload["artifacts"]["qd_archive"]["validation_status"] == "validated"
    assert status_payload["artifacts"]["allocation_ledger"]["validation_status"] == "validated"
    assert status_payload["artifacts"]["candidate_promotion_gates"]["validation_status"] == (
        "validated"
    )


def test_campaign_cli_status_reports_final_gate_failure_without_calling_it_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _passing_contract()
    path = campaign_contract_path(payload["campaign_id"], tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    _write_promotion_evidence(path, payload)
    gates_path = path.parent / "artifacts/statistical-family-gates.json"
    gates = json.loads(gates_path.read_text(encoding="utf-8"))
    gates["candidate_sharpe_excess_bil"]["H1C01"] = 1.0
    gates_path.write_text(json.dumps(gates), encoding="utf-8")
    monkeypatch.setattr("open_composer.cli.project_root", lambda: tmp_path)

    status = CliRunner().invoke(
        app,
        ["research", "campaign", "status", payload["campaign_id"], "--json"],
        catch_exceptions=False,
    )

    status_payload = json.loads(status.stdout)
    assert status.exit_code == 0
    assert status_payload["phase"] == "final_failed"
    assert status_payload["stage_validations"]["pre-oos"]["status"] == "ok"
    assert status_payload["stage_validations"]["final"]["status"] == "blocked"
    assert (
        "statistical_family_primary_sharpe_gate_failed:H1C01"
        in status_payload["stage_validations"]["final"]["blocked"]
    )


def test_campaign_cli_status_blocks_malformed_selection_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _passing_contract()
    path = campaign_contract_path(payload["campaign_id"], tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    (path.parent / "qd-archive.json").write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr("open_composer.cli.project_root", lambda: tmp_path)

    status = CliRunner().invoke(
        app,
        ["research", "campaign", "status", payload["campaign_id"], "--json"],
        catch_exceptions=False,
    )

    status_payload = json.loads(status.stdout)
    assert status.exit_code == 1
    assert status_payload["phase"] == "blocked"
    assert status_payload["artifacts"]["qd_archive"]["valid_json"] is False
    assert status_payload["frozen_oos_influences_selection"] is None


def test_research_design_has_typed_campaign_binding() -> None:
    design = ResearchDesign(
        iter_id="momentum_branch_r1",
        campaign_contract_path=(
            "reports/research/campaigns/momentum_qd_r1/research-campaign-contract.json"
        ),
    )

    assert design.campaign_contract_path.endswith("research-campaign-contract.json")
    assert research_design_requires_iteration_gate(design.model_dump(mode="json")) is True


@pytest.mark.parametrize(
    "command",
    [
        ["strategy", "factor-lab"],
        ["strategy", "train"],
        ["strategy", "backtest-walk-forward"],
        ["strategy", "evidence"],
        ["strategy", "promotion-report"],
        ["strategy", "optimize-universe", "--symbols", "SPY"],
        ["strategy", "optimize-horizons", "--symbols", "SPY"],
        ["strategy", "rotate-universe", "--symbols", "SPY"],
        ["strategy", "market-time"],
    ],
)
def test_research_cli_entrypoints_enforce_iteration_gate(
    command: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec_path = tmp_path / "candidate.yaml"

    def blocked_gate(_: Path) -> None:
        raise typer.BadParameter("sentinel iteration gate")

    monkeypatch.setattr("open_composer.cli._require_declared_iteration_gate", blocked_gate)
    result = CliRunner().invoke(app, [*command[:2], str(spec_path), *command[2:]])

    assert result.exit_code == 2
    assert "sentinel iteration gate" in result.output


def test_public_research_library_entrypoints_fail_before_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_composer.engines.backtest_engine import run_backtest
    from open_composer.research.evidence import build_strategy_evidence
    from open_composer.research.factor_lab import run_factor_lab
    from open_composer.research.horizon_optimizer import optimize_strategy_horizons
    from open_composer.research.ml_backend.evaluation import (
        compare_ml_to_baseline,
        train_strategy_model,
    )
    from open_composer.research.optimizer import optimize_strategy
    from open_composer.research.parameter_sweep import run_parameter_sweep
    from open_composer.research.promotion import build_promotion_report
    from open_composer.research.research_report import build_strategy_research_report
    from open_composer.research.rotation import run_rotation_research
    from open_composer.research.universe_optimizer import optimize_strategy_universe

    def blocked_gate(*_: Any, **__: Any) -> None:
        raise ValueError("sentinel direct iteration gate")

    gate_targets = [
        "open_composer.engines.backtest_engine.require_iteration_execution_gate",
        "open_composer.research.evidence.require_iteration_execution_gate",
        "open_composer.research.factor_lab.require_iteration_execution_gate",
        "open_composer.research.horizon_optimizer.require_iteration_execution_gate",
        "open_composer.research.ml_backend.evaluation.require_iteration_execution_gate",
        "open_composer.research.optimizer.require_iteration_execution_gate",
        "open_composer.research.parameter_sweep.require_iteration_execution_gate",
        "open_composer.research.promotion.require_iteration_execution_gate",
        "open_composer.research.research_report.require_iteration_execution_gate",
        "open_composer.research.rotation.require_iteration_execution_gate",
        "open_composer.research.universe_optimizer.require_iteration_execution_gate",
    ]
    for target in gate_targets:
        monkeypatch.setattr(target, blocked_gate)
    spec_path = tmp_path / "does-not-need-to-exist.yaml"
    calls = [
        lambda: run_backtest(spec_path, root=tmp_path),
        lambda: build_strategy_evidence(spec_path, tmp_path),
        lambda: run_factor_lab(spec_path, tmp_path),
        lambda: optimize_strategy_horizons(spec_path, tmp_path),
        lambda: train_strategy_model(spec_path, tmp_path),
        lambda: compare_ml_to_baseline(spec_path, tmp_path),
        lambda: optimize_strategy(spec_path, tmp_path),
        lambda: run_parameter_sweep(spec_path, {"entry.lookback": ["20"]}, tmp_path),
        lambda: build_promotion_report(spec_path, tmp_path),
        lambda: build_strategy_research_report(spec_path, tmp_path),
        lambda: run_rotation_research(spec_path, tmp_path),
        lambda: optimize_strategy_universe(spec_path, tmp_path),
    ]

    for call in calls:
        with pytest.raises(ValueError, match="sentinel direct iteration gate"):
            call()
